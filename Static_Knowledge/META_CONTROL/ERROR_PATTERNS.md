# ERROR PATTERNS - Known Issues & Solutions
**Purpose**: Quick reference for common errors in Ablage-System OCR

## GPU-Related Errors

### Error: CUDA Out of Memory (OOM)
```python
torch.cuda.OutOfMemoryError: CUDA out of memory.
```
**Root Cause**: GPU VRAM exceeded (>16GB on RTX 4080)

**Solution Pattern**:
```python
try:
    result = model.process_batch(images)
except torch.cuda.OutOfMemoryError:
    # Clear cache and reduce batch size
    torch.cuda.empty_cache()
    batch_size = max(1, current_batch_size // 2)
    result = model.process_batch(images[:batch_size])
```

**Prevention**:
- Monitor VRAM: Keep under 13.6GB (85% of 16GB)
- Use dynamic batch sizing
- Implement `gpu_memory_guard` context manager

---

### Error: GPU Not Detected
```
RuntimeError: CUDA not available
```
**Possible Causes**:
1. PyTorch CPU-only version installed
2. CUDA drivers not installed
3. Wrong PyTorch version for CUDA version

**Solution**:
```bash
# Check CUDA version
nvidia-smi

# Install correct PyTorch (for CUDA 12.x)
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

---

### Error: Multiple Processes Accessing GPU
```
RuntimeError: CUDA error: out of memory or device-side assert
```
**Root Cause**: Celery workers competing for GPU

**Solution**:
```bash
# Use solo pool for Celery
celery -A app.celery worker --pool=solo --concurrency=1
```

---

## German Text Processing Errors

### Error: Umlaut Corruption
```
'M\udcc3\udcbcller' instead of 'Müller'
```
**Root Cause**: Encoding mismatch (UTF-8 vs Latin-1)

**Solution Pattern**:
```python
import unicodedata

def fix_encoding(text: str) -> str:
    # Normalize to NFC (composed form)
    text = unicodedata.normalize('NFC', text)

    # Ensure UTF-8
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')

    return text
```

**Prevention**:
- Always use UTF-8 encoding explicitly
- Normalize all input text
- Validate with GermanValidator

---

### Error: ß (Eszett) Misrecognition
```
'Straße' → 'Strafie' or 'StraBe'
```
**Root Cause**: OCR backend confusion (ß looks like β or B)

**Solution Pattern**:
```python
# Post-processing correction
COMMON_ERRORS = {
    'Strafie': 'Straße',
    'StraBe': 'Straße',
    'Fufis': 'Füßis'
}

def correct_eszett(text: str) -> str:
    for wrong, correct in COMMON_ERRORS.items():
        text = text.replace(wrong, correct)

    # Intelligent correction with context
    if 'strass' in text.lower() and not 'straße' in text.lower():
        text = text.replace('strass', 'straß')

    return text
```

---

## Database Errors

### Error: Connection Pool Exhausted
```
sqlalchemy.exc.TimeoutError: QueuePool limit exceeded
```
**Root Cause**: Too many concurrent connections

**Solution**:
```python
# Increase pool size in config
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,  # Up from default 5
    max_overflow=40,
    pool_pre_ping=True  # Verify connections
)
```

---

### Error: Alembic Migration Conflict
```
alembic.util.exc.CommandError: Target database is not up to date.
```
**Solution**:
```bash
# Check current revision
alembic current

# Reset to head
alembic upgrade head

# If conflict persists, check history
alembic history
```

---

## API Errors

### Error: 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "text"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
**Root Cause**: Pydantic validation failed

**Solution**:
- Check request schema matches Pydantic model
- Use `/docs` endpoint to see expected schema
- Verify Content-Type header

---

### Error: 413 Request Entity Too Large
```
413 Request Entity Too Large
```
**Root Cause**: Document exceeds max upload size

**Solution**:
```python
# In FastAPI config
app = FastAPI()
app.add_middleware(
    # Increase max upload size
    HTTPMiddleware,
    max_upload_size=50 * 1024 * 1024  # 50MB
)
```

---

## Celery/Redis Errors

### Error: Redis Connection Refused
```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379
```
**Solution**:
```bash
# Start Redis
docker-compose up -d redis

# Or standalone
redis-server
```

---

### Error: Task Timeout
```
celery.exceptions.SoftTimeLimitExceeded
```
**Solution**:
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540  # 9 minutes soft limit
)
async def process_document_task(self, doc_id: str):
    # Implementation
    pass
```

---

## File Processing Errors

### Error: PDF Parsing Failed
```
PDFSyntaxError: Invalid PDF structure
```
**Solution**:
```python
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import pikepdf

def repair_pdf(pdf_path: str) -> str:
    """Attempt to repair corrupt PDF"""
    try:
        # Try with pikepdf (more robust)
        with pikepdf.open(pdf_path) as pdf:
            repaired_path = pdf_path.replace('.pdf', '_repaired.pdf')
            pdf.save(repaired_path)
            return repaired_path
    except Exception as e:
        logger.error(f"PDF repair failed: {e}")
        raise ValueError(f"Cannot process PDF: {pdf_path}")
```

---

## Testing Errors

### Error: Pytest Import Error
```
ModuleNotFoundError: No module named 'app'
```
**Solution**:
```bash
# Ensure PYTHONPATH includes project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or use pytest with src layout
pytest tests/ --import-mode=importlib
```

---

### Error: Async Tests Not Running
```
RuntimeError: no running event loop
```
**Solution**:
```python
# Install pytest-asyncio
pip install pytest-asyncio

# Mark tests correctly
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

---

## Recovery Procedures

### GPU OOM Recovery
```python
def emergency_gpu_recovery():
    """Emergency GPU cleanup procedure"""
    import gc
    import torch

    # Clear all allocations
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    # Force garbage collection
    gc.collect()

    # Reset statistics
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()

    logger.info("GPU memory emergency recovery completed")
```

### Application State Recovery
```python
def recover_application_state():
    """Recover from crashed state"""
    # 1. Clear stuck Celery tasks
    celery_app.control.purge()

    # 2. Reset Redis cache
    redis_client.flushdb()

    # 3. Check database connections
    await db.execute("SELECT 1")

    # 4. Reinitialize GPU if needed
    gpu_manager = GPUManager()
    gpu_manager.check_availability()

    logger.info("Application state recovered")
```

---

## Error Code Registry
```python
ERROR_CODES = {
    "E001": "GPU Out of Memory",
    "E002": "GPU Not Available",
    "E003": "Invalid German Text Encoding",
    "E004": "OCR Backend Timeout",
    "E005": "Database Connection Failed",
    "E006": "Redis Connection Failed",
    "E007": "Document Format Invalid",
    "E008": "File Size Exceeded",
    "E009": "GDPR Violation Detected",
    "E010": "Backend Selection Failed"
}
```

---

## Quick Diagnostics

### Health Check Command
```bash
# Comprehensive system check
curl -s http://localhost:8000/health | python -m json.tool
```

### GPU Status
```bash
# Detailed GPU info
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv

# From Python
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"
```

### Database Status
```bash
docker exec -it ablage-postgres psql -U postgres -c "\conninfo"
```

---
**Maintenance**: Update when new error patterns discovered
**Token Budget**: ~1.5K tokens
