# Async/Await Patterns - Ablage-System
**Version:** 1.0
**Status:** Production Reference
**Letzte Aktualisierung:** 2025-11-23
**Python Version:** 3.11+
**Framework:** FastAPI 0.110+

**Tags:** #async #patterns #python #fastapi #asyncio #performance #developer #high #static_knowledge

---

## Überblick

Ablage-System ist vollständig **async-first** designed. Dieses Dokument definiert Best Practices, Patterns und Anti-Patterns für asynchrone Programmierung im Projekt.

### Warum Async?

**Performance-Vorteile:**
```
Synchronous:  1 request → wait → 1 request → wait → ...
              Throughput: ~10 requests/s

Asynchronous: 100 requests → all processing concurrently
              Throughput: ~1000 requests/s (100x)
```

**Ablage-System Use Cases:**
- **I/O-bound operations:** Database queries, MinIO uploads, HTTP requests
- **Concurrent document processing:** 100 documents processed simultaneously
- **Real-time updates:** WebSocket connections for OCR progress
- **GPU task queuing:** Async wait while GPU processes

---

## Grundlagen

### Async/Await Syntax

```python
# ❌ Synchronous (blocking)
def process_document(doc_id: str) -> Result:
    document = db.query(Document).get(doc_id)  # Blocks thread
    file = storage.download(document.path)     # Blocks thread
    result = ocr.process(file)                  # Blocks thread
    return result

# ✅ Asynchronous (non-blocking)
async def process_document(doc_id: str) -> Result:
    document = await db.get(Document, doc_id)  # Yields control
    file = await storage.download(document.path) # Yields control
    result = await ocr.process(file)            # Yields control
    return result
```

### Event Loop

```python
import asyncio

# Event Loop basics
loop = asyncio.get_event_loop()
result = loop.run_until_complete(async_function())

# Modern Python 3.11+ (preferred)
result = asyncio.run(async_function())
```

---

## FastAPI Async Patterns

### 1. Async Route Handlers

```python
# app/api/v1/documents.py
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# ✅ Async route (preferred for I/O operations)
@router.post("/upload")
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    """Async upload: Non-blocking I/O."""

    # Async file read
    contents = await file.read()

    # Async storage
    storage_path = await storage_service.upload(contents, file.filename)

    # Async DB insert
    document = Document(filename=file.filename, storage_path=storage_path, user_id=current_user.id)
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Async task queue
    await celery_app.send_task('process_ocr', args=[str(document.id)])

    return DocumentResponse.from_orm(document)


# ⚠️ Sync route (only for CPU-bound, no I/O)
@router.get("/health")
def health_check() -> Dict[str, str]:
    """Sync route: No I/O, just returning static data."""
    return {"status": "healthy"}
```

**Rule:** Use `async def` for ANY route that does I/O (DB, Storage, HTTP, etc.)

### 2. Dependency Injection (Async)

```python
# app/api/dependencies.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_maker

async def get_db() -> AsyncSession:
    """Async database session dependency."""
    async with async_session_maker() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Async user authentication."""
    payload = jwt.decode(token, SECRET_KEY)
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(401, "Invalid credentials")

    return user
```

### 3. Background Tasks (FastAPI)

```python
from fastapi import BackgroundTasks

@router.post("/process")
async def trigger_processing(
    document_id: str,
    background_tasks: BackgroundTasks
):
    """Trigger processing in background."""

    # Add async background task
    background_tasks.add_task(process_document_background, document_id)

    return {"status": "processing started"}

async def process_document_background(document_id: str):
    """Runs after response sent."""
    await ocr_service.process(document_id)
```

---

## Database Async Patterns (SQLAlchemy 2.0)

### 1. Async Session Management

```python
# app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Async engine
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    echo=True,
    pool_size=20,
    max_overflow=40
)

# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Usage
async with async_session_maker() as session:
    result = await session.execute(select(Document))
    documents = result.scalars().all()
```

### 2. Async Queries

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ✅ Async SELECT
async def get_document(db: AsyncSession, doc_id: str) -> Optional[Document]:
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    return result.scalar_one_or_none()

# ✅ Async INSERT
async def create_document(db: AsyncSession, doc: DocumentCreate) -> Document:
    document = Document(**doc.dict())
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document

# ✅ Async UPDATE
async def update_document(db: AsyncSession, doc_id: str, updates: Dict) -> Document:
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    document = result.scalar_one()

    for key, value in updates.items():
        setattr(document, key, value)

    await db.commit()
    await db.refresh(document)
    return document

# ✅ Async DELETE
async def delete_document(db: AsyncSession, doc_id: str) -> None:
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    document = result.scalar_one()
    await db.delete(document)
    await db.commit()
```

### 3. Async Relationships

```python
from sqlalchemy.orm import selectinload

# ✅ Eager loading (avoid N+1)
async def get_document_with_ocr_results(db: AsyncSession, doc_id: str) -> Document:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.ocr_results))
        .where(Document.id == doc_id)
    )
    return result.scalar_one()

# ❌ N+1 Problem
async def bad_example(db: AsyncSession):
    documents = await db.execute(select(Document))
    for doc in documents.scalars():
        # This triggers a new query for EACH document!
        ocr_results = await db.execute(
            select(OCRResult).where(OCRResult.document_id == doc.id)
        )
```

---

## Concurrent Operations

### 1. asyncio.gather (Parallel Execution)

```python
import asyncio

# ✅ Run multiple async operations concurrently
async def process_multiple_documents(document_ids: List[str]) -> List[Result]:
    """Process documents in parallel."""

    tasks = [process_document(doc_id) for doc_id in document_ids]

    # All run concurrently, wait for all to complete
    results = await asyncio.gather(*tasks)

    return results

# ✅ With error handling
async def process_with_error_handling(document_ids: List[str]):
    tasks = [process_document(doc_id) for doc_id in document_ids]

    # return_exceptions=True: Don't fail all if one fails
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Document {document_ids[i]} failed: {result}")
        else:
            logger.info(f"Document {document_ids[i]} processed successfully")

    return results
```

### 2. asyncio.create_task (Fire and Forget)

```python
# ✅ Start task, don't wait for completion
async def trigger_background_processing(document_id: str):
    """Start processing but don't block."""

    # Create task
    task = asyncio.create_task(process_document(document_id))

    # Optionally: Add callback
    task.add_done_callback(on_processing_complete)

    # Return immediately
    return {"status": "processing started", "task_id": id(task)}

def on_processing_complete(task: asyncio.Task):
    """Called when task finishes."""
    try:
        result = task.result()
        logger.info(f"Processing completed: {result}")
    except Exception as e:
        logger.error(f"Processing failed: {e}")
```

### 3. asyncio.wait (Advanced Control)

```python
import asyncio

# ✅ Wait for first completion
async def process_with_timeout(document_id: str, timeout: float = 30.0):
    """Process with timeout."""

    task = asyncio.create_task(process_document(document_id))

    done, pending = await asyncio.wait(
        [task],
        timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED
    )

    if task in done:
        return task.result()
    else:
        task.cancel()
        raise TimeoutError(f"Processing exceeded {timeout}s")

# ✅ Wait for first success (redundancy)
async def process_with_redundancy(document_id: str):
    """Try multiple backends, use first success."""

    tasks = [
        process_with_deepseek(document_id),
        process_with_got_ocr(document_id),
        process_with_surya(document_id)
    ]

    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED
    )

    # Cancel pending tasks
    for task in pending:
        task.cancel()

    # Return first result
    return list(done)[0].result()
```

---

## Celery + Async Integration

### Async Celery Tasks

```python
# app/workers/ocr_tasks.py
from celery import Celery
import asyncio

celery_app = Celery('ablage', broker='redis://localhost:6379/0')

@celery_app.task
def process_document_task(document_id: str) -> Dict:
    """
    Celery task wrapper (sync) around async function.

    Celery doesn't natively support async, so we wrap it.
    """

    # Run async function in event loop
    result = asyncio.run(process_document_async(document_id))

    return result

async def process_document_async(document_id: str) -> Dict:
    """Actual async implementation."""

    # Async DB
    async with async_session_maker() as db:
        document = await get_document(db, document_id)

    # Async OCR
    result = await ocr_service.process(document)

    # Async storage
    async with async_session_maker() as db:
        await save_ocr_result(db, result)

    return result
```

---

## GPU Operations (Async Wrapper)

```python
# app/utils/gpu_async.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
import torch

# Thread pool for blocking GPU operations
gpu_executor = ThreadPoolExecutor(max_workers=1)

async def process_with_gpu_async(image: np.ndarray, model: nn.Module) -> torch.Tensor:
    """
    Wrap synchronous GPU operation in async.

    GPU operations (PyTorch) are blocking, so we run them in thread pool.
    """

    loop = asyncio.get_event_loop()

    # Run blocking operation in executor
    result = await loop.run_in_executor(
        gpu_executor,
        _process_gpu_sync,
        image,
        model
    )

    return result

def _process_gpu_sync(image: np.ndarray, model: nn.Module) -> torch.Tensor:
    """Blocking GPU operation."""
    with torch.no_grad():
        tensor = torch.from_numpy(image).cuda()
        output = model(tensor)
    return output
```

---

## Error Handling

### 1. Try/Except in Async

```python
async def robust_processing(document_id: str) -> Result:
    """Async error handling."""

    try:
        result = await process_document(document_id)
        return result

    except DocumentNotFoundError as e:
        logger.error(f"Document {document_id} not found")
        raise HTTPException(404, str(e))

    except OCRProcessingError as e:
        logger.exception("OCR processing failed")
        # Try fallback backend
        result = await process_with_fallback(document_id)
        return result

    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(500, "Internal server error")

    finally:
        # Cleanup always runs
        await cleanup_temp_files(document_id)
```

### 2. Retry Pattern

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def process_with_retry(document_id: str) -> Result:
    """Retry on failure with exponential backoff."""

    result = await process_document(document_id)

    if result.confidence < 0.7:
        raise ProcessingQualityError("Low confidence result")

    return result
```

---

## Testing Async Code

### 1. pytest-asyncio

```python
# tests/test_document_service.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_upload_document():
    """Test async document upload."""

    async with AsyncClient(app=app, base_url="http://test") as client:
        files = {"file": ("test.pdf", open("test.pdf", "rb"))}

        response = await client.post("/api/v1/documents/upload", files=files)

        assert response.status_code == 201
        assert "id" in response.json()

@pytest.mark.asyncio
async def test_concurrent_uploads():
    """Test multiple concurrent uploads."""

    async with AsyncClient(app=app, base_url="http://test") as client:
        files = [("test.pdf", open(f"test{i}.pdf", "rb")) for i in range(10)]

        tasks = [
            client.post("/api/v1/documents/upload", files={"file": f})
            for f in files
        ]

        responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 201 for r in responses)
```

### 2. Mocking Async Functions

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    """Mock async dependencies."""

    with patch('app.services.ocr_service.process', new_callable=AsyncMock) as mock_process:
        mock_process.return_value = {"text": "mocked result"}

        result = await process_document("test_id")

        assert result["text"] == "mocked result"
        mock_process.assert_called_once_with("test_id")
```

---

## Anti-Patterns (Avoid!)

### ❌ Blocking in Async Function

```python
# ❌ BAD: Blocking call in async function
async def bad_example():
    result = requests.get("http://api.example.com")  # BLOCKS EVENT LOOP!
    return result.json()

# ✅ GOOD: Use async HTTP client
async def good_example():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://api.example.com")
        return response.json()
```

### ❌ Mixing Sync/Async DB Sessions

```python
# ❌ BAD: Sync DB in async route
@router.get("/documents")
async def get_documents(db: Session = Depends(get_sync_db)):  # Wrong!
    documents = db.query(Document).all()  # Blocks!
    return documents

# ✅ GOOD: Async DB in async route
@router.get("/documents")
async def get_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document))
    documents = result.scalars().all()
    return documents
```

### ❌ Forgetting await

```python
# ❌ BAD: Forgot await
async def bad_example():
    result = async_function()  # Returns coroutine, not result!
    print(result)  # <coroutine object>

# ✅ GOOD: Use await
async def good_example():
    result = await async_function()  # Actual result
    print(result)
```

---

## Performance Optimization

### 1. Connection Pooling

```python
# ✅ Database connection pool
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,        # Concurrent connections
    max_overflow=40,     # Extra connections if pool exhausted
    pool_pre_ping=True   # Verify connection before use
)
```

### 2. Batch Operations

```python
# ✅ Batch database inserts
async def bulk_insert(db: AsyncSession, documents: List[DocumentCreate]):
    """Insert multiple documents efficiently."""

    db_documents = [Document(**doc.dict()) for doc in documents]
    db.add_all(db_documents)
    await db.commit()
```

### 3. Caching

```python
from functools import lru_cache
import asyncio

# ✅ Async cache decorator
def async_lru_cache(maxsize=128):
    def decorator(func):
        cache = {}

        async def wrapper(*args):
            if args in cache:
                return cache[args]

            result = await func(*args)
            cache[args] = result

            if len(cache) > maxsize:
                cache.pop(next(iter(cache)))

            return result

        return wrapper
    return decorator

@async_lru_cache(maxsize=100)
async def get_cached_document(doc_id: str) -> Document:
    """Cached async document retrieval."""
    async with async_session_maker() as db:
        return await get_document(db, doc_id)
```

---

## Verwandte Dokumentation

- **[agent_implementation_patterns.md](../Architecture/agent_implementation_patterns.md)** - Agent async patterns
- **[component_integration_map.md](../../Relations/Integration_Maps/component_integration_map.md)** - System integration

---

## Changelog

| Version | Datum | Änderungen | Autor |
|---------|-------|-----------|-------|
| 1.0 | 2025-11-23 | Initial async patterns guide | Development Team |

---

**Maintainer:** Development Team
**Review:** Quarterly
**Nächstes Review:** 2026-02-23
