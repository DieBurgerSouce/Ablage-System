# Ablage-System Quick Reference Card

**Version:** 1.0
**Last Updated:** 2025-01-23
**Target Audience:** Developers, DevOps Engineers, System Administrators

---

## 🚀 Quick Start Commands

### Development Environment

```bash
# Start entire stack
docker-compose up -d

# Start backend only (hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (GPU tasks)
celery -A app.celery worker --loglevel=info --concurrency=1 --pool=solo

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Type checking
mypy app/

# Linting and formatting
ruff check .
ruff format .
```

### Database Operations

```bash
# Apply migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback one migration
alembic downgrade -1

# Check current migration
alembic current

# Backup database
docker exec ablage-postgres pg_dump -U postgres ablage > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore database
docker exec -i ablage-postgres psql -U postgres ablage < backup_20250123_143000.sql
```

### GPU Operations

```bash
# Check GPU status
nvidia-smi

# Monitor GPU in real-time
watch -n 1 nvidia-smi

# Check CUDA in Python
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"

# Clear GPU cache (emergency)
docker exec ablage-backend python -c "import torch; torch.cuda.empty_cache()"
```

---

## 📁 Key File Locations

### Application Structure

```
app/
├── main.py                           # FastAPI entry point
├── api/v1/
│   ├── documents.py                  # Document endpoints (L89-L412)
│   ├── auth.py                       # Authentication (L45-L201)
│   └── users.py                      # User management (L56-L267)
├── services/ocr/
│   ├── orchestrator.py               # Backend selection logic
│   ├── deepseek.py                   # DeepSeek integration
│   ├── got_ocr.py                    # GOT-OCR integration
│   └── surya_docling.py              # Surya+Docling pipeline
├── core/
│   ├── config.py                     # Configuration
│   ├── security.py                   # JWT auth
│   └── logging.py                    # Structured logging
└── db/
    ├── models.py                     # SQLAlchemy models
    └── schemas.py                    # Pydantic schemas
```

### Documentation

```
KNOWLEDGE_ARCHITECTURE.md             # Architecture overview
Meta_Layer/Indexes/master_navigation_index.yaml  # Complete file catalog
Meta_Layer/Knowledge_Graphs/system_architecture_visual_map.md  # Visual diagrams
Static_Knowledge/ADRs/                # Architecture Decision Records
Static_Knowledge/German_Business/     # German business rules
```

### Configuration Files

```
.env                                  # Environment variables (NEVER commit!)
.env.example                          # Template for environment variables
docker-compose.yml                    # Docker services configuration
requirements.txt                      # Python dependencies
pyproject.toml                        # Python project config + tool settings
```

---

## 🔑 Critical Configuration Values

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ablage

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# JWT
SECRET_KEY=your-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# OCR
DEFAULT_OCR_BACKEND=deepseek
GPU_ENABLED=true
MAX_BATCH_SIZE=16

# GDPR
DATA_RETENTION_DAYS=3650  # 10 years for invoices (§14 UStG)
ANONYMIZATION_DELAY_DAYS=30
```

### GPU Thresholds

```python
VRAM_THRESHOLDS = {
    "safe": 0.70,        # < 70% VRAM - Normal operation
    "elevated": 0.85,    # 70-85% - Start reducing batch size
    "critical": 0.90,    # > 85% - Force batch size 1 or fallback to CPU
}

BATCH_SIZE_BY_COMPLEXITY = {
    "simple": 16,        # Standard documents, no tables/images
    "medium": 8,         # Some tables or images
    "complex": 4,        # Multi-page with tables, images, and complex layout
}

GPU_REQUIREMENTS_GB = {
    "deepseek": 12,      # DeepSeek-Janus-Pro 1.3B
    "got_ocr": 10,       # GOT-OCR 2.0 600M
    "surya": 0,          # CPU-only fallback (or 4GB GPU for acceleration)
}
```

### Performance Targets

```yaml
API Response Times (P95):
  health_check: "< 50ms"
  document_upload: "< 500ms"
  document_retrieval: "< 100ms (cached), < 300ms (db)"
  search_query: "< 500ms"

OCR Processing Times:
  deepseek: "< 2.8s per page (GPU)"
  got_ocr: "< 0.8s per page (GPU)"
  surya: "< 5.0s per page (CPU), < 1.9s (GPU)"

Throughput:
  concurrent_users: "100+"
  documents_per_hour: "500+ (GPU), 100+ (CPU)"
  api_requests_per_second: "1000+"
```

### Rate Limits

```python
RATE_LIMITS = {
    "auth/register": "5 requests per 15 minutes per IP",
    "auth/login": "5 attempts per 15 minutes per IP",
    "documents/upload": "10 documents per minute per user",
    "api_general": {
        "free_tier": "10 requests/minute",
        "standard_tier": "60 requests/minute",
        "enterprise_tier": "300 requests/minute",
    }
}
```

---

## 🏥 Health Check Endpoints

### Quick Health Status

```bash
# Overall health
curl https://app.ablage-system.de/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-01-23T14:30:00Z",
  "checks": {
    "database": true,
    "redis": true,
    "gpu": true,
    "storage": true
  }
}

# Prometheus metrics
curl https://app.ablage-system.de/metrics

# API documentation
https://app.ablage-system.de/docs
```

### Health Check Components

| Service | Endpoint | Expected Response | Unhealthy Threshold |
|---------|----------|-------------------|---------------------|
| Database | `/health` → checks.database | `true` | Connection timeout > 5s |
| Redis | `/health` → checks.redis | `true` | Ping failed |
| GPU | `/health` → checks.gpu | `true` | CUDA unavailable or VRAM > 95% |
| MinIO | `/health` → checks.storage | `true` | Bucket list failed |
| Disk | `/health` → checks.disk_space | `true` | Free space < 10% |

---

## 🐛 Quick Troubleshooting

### Problem: GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Check CUDA in Docker
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Check Docker GPU access
docker exec ablage-backend python -c "import torch; print(torch.cuda.is_available())"

# Fix: Ensure NVIDIA Container Toolkit installed
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Problem: GPU Out of Memory (OOM)

```bash
# Immediate fix: Clear GPU cache
docker exec ablage-backend python -c "import torch; torch.cuda.empty_cache()"

# Check current GPU usage
docker exec ablage-backend python -c "import torch; print(f'Allocated: {torch.cuda.memory_allocated()/1024**3:.2f} GB'); print(f'Reserved: {torch.cuda.memory_reserved()/1024**3:.2f} GB')"

# Reduce batch size (edit .env)
MAX_BATCH_SIZE=4  # or 1 for extreme cases

# Restart worker
docker-compose restart worker
```

### Problem: Celery Worker Crashed

```bash
# Check worker logs
docker-compose logs worker

# Check worker status
docker-compose ps worker

# Restart worker
docker-compose restart worker

# Force recreate worker (if corrupted)
docker-compose stop worker
docker-compose rm -f worker
docker-compose up -d worker
```

### Problem: Database Connection Pool Exhausted

```python
# Check pool status
from sqlalchemy import inspect
inspector = inspect(engine)
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checked_out_connections}")
print(f"Overflow: {pool.overflow()}")

# Fix: Increase pool size in app/core/config.py
DATABASE_POOL_SIZE = 20  # Increase from default 5
DATABASE_MAX_OVERFLOW = 40
```

### Problem: MinIO Connection Failed

```bash
# Check MinIO status
docker-compose ps minio

# Check MinIO logs
docker-compose logs minio

# Test MinIO connection
curl http://localhost:9000/minio/health/live

# Access MinIO console
http://localhost:9001
# Default credentials: minioadmin / minioadmin
```

### Problem: Redis Connection Failed

```bash
# Check Redis status
docker-compose ps redis

# Test Redis connection
docker exec ablage-redis redis-cli ping
# Expected: PONG

# Check Redis memory usage
docker exec ablage-redis redis-cli INFO memory

# Clear Redis cache (emergency only)
docker exec ablage-redis redis-cli FLUSHALL
```

---

## 🔒 Security Quick Reference

### JWT Token Management

```python
# Token expiration (app/core/config.py)
ACCESS_TOKEN_EXPIRE_MINUTES = 15   # Short-lived access tokens
REFRESH_TOKEN_EXPIRE_DAYS = 7      # Long-lived refresh tokens

# Token validation
from app.core.security import verify_token
payload = verify_token(token)  # Raises HTTPException if invalid
```

### Password Requirements

```python
MIN_PASSWORD_LENGTH = 8
REQUIRES_UPPERCASE = True
REQUIRES_LOWERCASE = True
REQUIRES_DIGIT = True
REQUIRES_SPECIAL_CHAR = False  # Optional for German users
```

### API Authentication

```bash
# Register user
curl -X POST https://app.ablage-system.de/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "company_name": "Example GmbH",
    "consent_terms": true,
    "consent_privacy": true
  }'

# Login
curl -X POST https://app.ablage-system.de/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123"
  }'

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer"
}

# Authenticated request
curl -X GET https://app.ablage-system.de/api/v1/users/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 🇩🇪 German Business Rules

### USt-IdNr (Umsatzsteuer-Identifikationsnummer) Validation

```python
import re

def validate_ust_id(ust_id: str) -> bool:
    """Validate German USt-IdNr (DE + 9 digits)."""
    return bool(re.match(r"^DE\d{9}$", ust_id))

# Examples:
validate_ust_id("DE123456789")  # ✅ Valid
validate_ust_id("DE12345678")   # ❌ Invalid (only 8 digits)
validate_ust_id("AT123456789")  # ❌ Invalid (wrong country code)
```

### IBAN Validation

```python
def validate_iban(iban: str) -> bool:
    """Validate IBAN using mod 97 checksum."""
    iban = iban.replace(" ", "").upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", iban):
        return False

    # Move first 4 chars to end
    rearranged = iban[4:] + iban[:4]

    # Convert letters to numbers (A=10, B=11, ..., Z=35)
    numeric = ""
    for char in rearranged:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - ord('A') + 10)

    # Check mod 97 = 1
    return int(numeric) % 97 == 1

# Example:
validate_iban("DE89 3704 0044 0532 0130 00")  # ✅ Valid
```

### German Date Formats

```python
from datetime import datetime

# Parse German date format (DD.MM.YYYY)
date_str = "23.01.2025"
date_obj = datetime.strptime(date_str, "%d.%m.%Y")

# Format as German date
formatted = date_obj.strftime("%d.%m.%Y")  # "23.01.2025"

# Parse German datetime with time
datetime_str = "23.01.2025 14:30"
datetime_obj = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
```

### Currency Formatting (German)

```python
def format_german_currency(amount: float) -> str:
    """Format amount as German currency (1.234,56 €)."""
    # German uses comma for decimal, dot for thousands
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"

# Examples:
format_german_currency(1234.56)   # "1.234,56 €"
format_german_currency(999.99)    # "999,99 €"
format_german_currency(1000000)   # "1.000.000,00 €"
```

---

## 📊 OCR Backend Selection Logic

### Decision Tree (Simplified)

```
1. Is GPU available?
   ├─ NO  → Route to Surya (CPU)
   └─ YES → Continue to step 2

2. Document complexity?
   ├─ SIMPLE (no tables/images, clean text)
   │   └─ User tier?
   │       ├─ FREE → GOT-OCR (fast, 5.9% CER)
   │       └─ PAID → DeepSeek (accurate, 2.8% CER)
   │
   ├─ MEDIUM (some tables or images)
   │   └─ Accuracy vs Speed preference?
   │       ├─ SPEED → GOT-OCR
   │       └─ ACCURACY → DeepSeek
   │
   └─ COMPLEX (multi-page, tables, images, Fraktur)
       └─ DeepSeek (highest accuracy)

3. VRAM check before processing
   ├─ VRAM < 70% → Process with selected backend
   ├─ VRAM 70-85% → Reduce batch size, process
   └─ VRAM > 85% → Force batch size 1 or fallback to CPU
```

### Backend Characteristics

| Backend | CER | Speed | VRAM | Best For |
|---------|-----|-------|------|----------|
| **DeepSeek-Janus-Pro** | 2.8% | 2.8s/page | 12GB | Complex layouts, Fraktur, high accuracy |
| **GOT-OCR 2.0** | 5.9% | 0.8s/page | 10GB | Simple documents, fast processing |
| **Surya + Docling** | 8.7% | 5.0s CPU<br/>1.9s GPU | 0GB CPU<br/>4GB GPU | Fallback, layout analysis |

### Manual Backend Selection (API)

```bash
# Upload with specific backend
curl -X POST https://app.ablage-system.de/api/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@rechnung.pdf" \
  -F "ocr_backend=deepseek"  # or "got_ocr" or "surya"

# Auto-selection (recommended)
curl -X POST https://app.ablage-system.de/api/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@rechnung.pdf" \
  -F "ocr_backend=auto"
```

---

## 🔄 Common Workflows

### 1. Deploying New Version

```bash
# Pre-deployment
1. Create backup
   docker exec ablage-postgres pg_dump -U postgres ablage > backup_$(date +%Y%m%d_%H%M%S).sql

2. Run tests on staging
   pytest tests/ -v

3. Check GPU availability
   nvidia-smi

# Deployment
4. Stop workers (prevent new jobs)
   docker-compose stop worker

5. Apply database migrations
   docker exec ablage-backend alembic upgrade head

6. Update backend (rolling update)
   docker-compose up -d --no-deps backend

7. Wait for health check
   curl -f https://app.ablage-system.de/health || echo "Health check failed"

8. Restart workers
   docker-compose up -d worker

# Post-deployment
9. Run smoke tests
   pytest tests/smoke/ -v

10. Monitor logs for 15 minutes
    docker-compose logs -f --tail=100
```

### 2. Processing a Document (Manual Test)

```python
import httpx
import asyncio

async def process_document():
    async with httpx.AsyncClient() as client:
        # 1. Login
        response = await client.post(
            "https://app.ablage-system.de/api/v1/auth/login",
            json={"email": "test@example.com", "password": "password"}
        )
        token = response.json()["access_token"]

        # 2. Upload document
        files = {"file": open("test_invoice.pdf", "rb")}
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.post(
            "https://app.ablage-system.de/api/v1/documents",
            files=files,
            headers=headers
        )
        doc_id = response.json()["document_id"]
        print(f"Uploaded document: {doc_id}")

        # 3. Poll for completion
        while True:
            response = await client.get(
                f"https://app.ablage-system.de/api/v1/documents/{doc_id}",
                headers=headers
            )
            status = response.json()["status"]
            print(f"Status: {status}")

            if status in ["valid", "validation_failed", "failed"]:
                break

            await asyncio.sleep(2)

        # 4. Get results
        result = response.json()
        print(f"Extracted text: {result['entities']['extracted_text'][:100]}...")

asyncio.run(process_document())
```

### 3. Investigating Performance Issues

```bash
# 1. Check system resources
docker stats

# 2. Check GPU usage
nvidia-smi

# 3. Check database connections
docker exec ablage-postgres psql -U postgres -d ablage -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# 4. Check Redis memory
docker exec ablage-redis redis-cli INFO memory

# 5. Check Celery queue length
docker exec ablage-redis redis-cli LLEN celery

# 6. Check slow API endpoints (if using Prometheus)
curl -s https://app.ablage-system.de/metrics | grep http_request_duration

# 7. Profile Python code
python -m cProfile -o profile.stats app/services/ocr/deepseek.py
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative'); p.print_stats(20)"
```

---

## 📈 Monitoring Key Metrics

### System Metrics (via Prometheus)

```promql
# API request rate
rate(http_requests_total[5m])

# API P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# OCR processing time by backend
histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket{backend="deepseek"}[5m]))

# GPU memory usage
gpu_memory_usage_bytes / gpu_memory_total_bytes

# Celery queue length
document_queue_length

# Error rate
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
```

### Health Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| API P95 Latency | < 300ms | 300-500ms | > 500ms |
| GPU VRAM Usage | < 70% | 70-85% | > 85% |
| CPU Usage | < 70% | 70-85% | > 85% |
| Disk Free Space | > 20% | 10-20% | < 10% |
| Database Connections | < 50% pool | 50-80% pool | > 80% pool |
| Error Rate | < 0.1% | 0.1-1% | > 1% |
| Queue Length | < 10 | 10-50 | > 50 |

---

## 🚨 Emergency Procedures

### System Overload

```bash
# 1. Stop accepting new uploads (emergency maintenance mode)
docker-compose stop nginx  # or backend if no nginx

# 2. Clear Celery queue (drastic)
docker exec ablage-redis redis-cli DEL celery

# 3. Restart workers
docker-compose restart worker

# 4. Clear GPU cache
docker exec ablage-backend python -c "import torch; torch.cuda.empty_cache()"

# 5. Resume operations gradually
docker-compose start backend
# Monitor for 5 minutes before enabling uploads
```

### Data Breach Response

```bash
# 1. Isolate system (disconnect from network)
docker-compose down

# 2. Capture logs
docker-compose logs > incident_logs_$(date +%Y%m%d_%H%M%S).txt

# 3. Backup database (preserve evidence)
docker exec ablage-postgres pg_dump -U postgres ablage > forensic_backup_$(date +%Y%m%d_%H%M%S).sql

# 4. Contact security team
# 5. Review GDPR breach notification requirements (Art. 33)
# 6. Document incident timeline
# 7. Implement fix
# 8. Resume operations only after security clearance
```

### Database Corruption

```bash
# 1. Stop all services
docker-compose stop backend worker

# 2. Attempt repair
docker exec ablage-postgres reindexdb -U postgres ablage

# 3. If repair fails, restore from backup
docker exec -i ablage-postgres psql -U postgres ablage < backup_20250123_143000.sql

# 4. Verify data integrity
docker exec ablage-postgres psql -U postgres -d ablage -c \
  "SELECT COUNT(*) FROM documents WHERE status = 'processing' AND updated_at < NOW() - INTERVAL '1 hour';"

# 5. Resume operations
docker-compose start backend worker
```

---

## 📞 Support Contacts

### Escalation Levels

| Level | Scope | Response Time | Contact |
|-------|-------|---------------|---------|
| **L1** | General issues, questions | 4 hours (business hours) | Team Lead |
| **L2** | GPU OOM, performance degradation | 1 hour | DevOps Team |
| **L3** | Data breach, system down | 15 minutes | CTO, Security Team |

### On-Call Rotation

```bash
# Check current on-call engineer
curl https://oncall.ablage-system.de/api/v1/current

# Trigger incident (emergency only)
curl -X POST https://oncall.ablage-system.de/api/v1/incidents \
  -H "Authorization: Bearer <token>" \
  -d '{
    "title": "Production API down",
    "severity": "critical",
    "description": "All API endpoints returning 502"
  }'
```

---

## 🧪 Testing Commands

### Unit Tests

```bash
# All unit tests
pytest tests/unit/ -v

# Specific module
pytest tests/unit/services/test_ocr_orchestrator.py -v

# With coverage
pytest tests/unit/ --cov=app --cov-report=term-missing
```

### Integration Tests

```bash
# All integration tests
pytest tests/integration/ -v --tb=short

# Specific integration test
pytest tests/integration/test_ocr_pipeline.py -v
```

### GPU Tests (Requires GPU)

```bash
# Skip if no GPU
pytest tests/gpu/ -v

# Force run (will fail if no GPU)
pytest tests/gpu/ -v --run-gpu-tests
```

### Performance Tests

```bash
# Load test (requires locust)
locust -f tests/performance/locustfile.py --host=https://app.ablage-system.de

# Benchmark OCR backends
python tests/performance/benchmark_ocr.py
```

---

## 🔗 Useful Links

### Documentation

- **Knowledge Architecture**: `KNOWLEDGE_ARCHITECTURE.md`
- **Master Index**: `Meta_Layer/Indexes/master_navigation_index.yaml`
- **Visual Diagrams**: `Meta_Layer/Knowledge_Graphs/system_architecture_visual_map.md`
- **API Docs**: `https://app.ablage-system.de/docs` (Swagger UI)

### External Resources

- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/
- **Celery**: https://docs.celeryq.dev/
- **PostgreSQL**: https://www.postgresql.org/docs/16/
- **MinIO**: https://min.io/docs/
- **GOT-OCR 2.0**: https://github.com/ucaslcl/GOT-OCR2.0
- **Surya**: https://github.com/VikParuchuri/surya
- **Docling**: https://github.com/DS4SD/docling

### Internal Tools

- **Grafana**: `https://monitoring.ablage-system.de`
- **Prometheus**: `https://prometheus.ablage-system.de`
- **MinIO Console**: `http://localhost:9001` (dev)
- **Redis Commander**: `http://localhost:8081` (dev)

---

## 📝 Quick Notes

### German Text Processing

```python
# Normalize umlauts (NFC form)
import unicodedata
text = unicodedata.normalize('NFC', text)

# Common German patterns
GERMAN_PATTERNS = {
    "date": r"\d{1,2}\.\d{1,2}\.\d{4}",  # DD.MM.YYYY
    "currency": r"\d{1,3}(?:\.\d{3})*,\d{2}\s*€",  # 1.234,56 €
    "ust_id": r"DE\d{9}",  # USt-IdNr
    "phone": r"\+49\s?\d{2,5}\s?\d{3,10}",  # German phone
}
```

### GDPR Compliance Quick Checks

```python
# Check retention policy
from datetime import datetime, timedelta
retention_date = datetime.now() - timedelta(days=3650)  # 10 years
old_invoices = await db.execute(
    select(Document).where(
        Document.document_type == "invoice",
        Document.invoice_date < retention_date
    )
)
# Should be empty (auto-deleted)

# Verify consent records exist
user = await db.get(User, user_id)
assert user.consent_terms == True
assert user.consent_privacy == True
assert user.consent_date is not None
```

### Performance Optimization Tips

1. **Use async/await everywhere** - Avoid blocking I/O
2. **Batch GPU operations** - Process multiple documents together
3. **Cache frequently accessed data** - Use Redis for hot data
4. **Lazy load models** - Load OCR models only when needed
5. **Monitor VRAM** - Keep under 85% to avoid OOM
6. **Use connection pools** - Reuse database connections
7. **Enable compression** - Reduce network transfer for large files

---

**End of Quick Reference Card**

**Version:** 1.0
**Maintained By:** Development Team
**Last Review:** 2025-01-23
**Next Review:** 2025-04-23 (Quarterly)

For detailed documentation, see `KNOWLEDGE_ARCHITECTURE.md`
