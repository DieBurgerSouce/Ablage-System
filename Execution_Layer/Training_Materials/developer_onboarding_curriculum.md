# Developer Onboarding Curriculum
**Ablage-System - Entwickler Einarbeitung**

Version: 1.0
Last Updated: 2025-01-23
Owner: Engineering Team
Duration: 4 weeks (80 hours)
Prerequisites: Python 3.11+, Docker, Git, REST APIs

---

## Course Overview

### Learning Objectives
By the end of this curriculum, you will be able to:
- Understand Ablage-System architecture and components
- Set up complete local development environment
- Implement new features following project standards
- Debug common issues independently
- Write tests and maintain code quality
- Contribute to code reviews effectively
- Deploy changes safely to production

### Time Commitment
- **Week 1:** System Architecture & Setup (20 hours)
- **Week 2:** Backend Development (20 hours)
- **Week 3:** Advanced Topics (20 hours)
- **Week 4:** Project Work (20 hours)

---

## Week 1: System Architecture & Setup

### Day 1: Welcome & Orientation (4 hours)

**Morning: Introduction (2 hours)**
- [ ] Team introduction and meet & greet
- [ ] Review company values and engineering culture
- [ ] Overview of Ablage-System purpose and users
- [ ] Tour of codebase structure

**Reading Assignment:**
1. [CLAUDE.md](../../CLAUDE.md) - Full project context (60 min)
2. [ARCHITECTURE.md](../../Static_Knowledge/Architecture_Decisions/system_architecture.md) (45 min)
3. [GETTING_STARTED.md](../../GETTING_STARTED.md) (15 min)

**Afternoon: Development Environment Setup (2 hours)**
```bash
# Clone repository
git clone https://github.com/company/ablage-system.git
cd ablage-system

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install

# Copy environment variables
cp .env.example .env
# Edit .env with your local settings

# Start development environment
docker-compose up -d

# Verify services running
docker-compose ps
curl http://localhost:8000/health
```

**✅ Day 1 Checklist:**
- [ ] Environment set up successfully
- [ ] All services running (backend, postgres, redis, minio, worker)
- [ ] Health check returns `{"status": "healthy"}`
- [ ] Can access MinIO console at http://localhost:9001

---

### Day 2: Architecture Deep Dive (4 hours)

**Morning: System Components (2 hours)**

**Study Materials:**
1. [System Architecture Visual Map](../../Meta_Layer/Knowledge_Graphs/system_architecture_visual_map.md)
2. [OCR Backend Selection ADR](../../Static_Knowledge/Architecture_Decisions/ADR_003_ocr_backend_selection.md)
3. [Database Architecture](../../Static_Knowledge/Technical_Details/database_architecture.md)

**Exercise 1: Component Identification**
```bash
# Identify each service's role
docker-compose ps

# Trace a document processing request:
# 1. Upload → FastAPI backend → MinIO storage → PostgreSQL metadata
# 2. Queue → Celery worker → GPU OCR → Result storage
# 3. Retrieval → Cache (Redis) → Database → MinIO

# Draw this flow on paper or digital whiteboard
```

**Afternoon: Data Flow Tracing (2 hours)**

**Exercise 2: Follow a Request**
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG

# Upload a test document
curl -X POST http://localhost:8000/api/v1/documents/ \
  -F "file=@tests/fixtures/sample_de.pdf" \
  -H "Authorization: Bearer dev_token"

# Watch logs in real-time (3 terminals)
# Terminal 1: Backend
docker-compose logs -f backend

# Terminal 2: Worker
docker-compose logs -f worker

# Terminal 3: Database
docker-compose logs -f postgres

# Document the flow in your notes
```

**✅ Day 2 Checklist:**
- [ ] Can explain all 5 major components (API, Worker, DB, Cache, Storage)
- [ ] Understand OCR backend selection logic
- [ ] Traced complete document processing flow
- [ ] Drawn architecture diagram

---

### Day 3: Code Standards & Best Practices (4 hours)

**Morning: Python Code Style (2 hours)**

**Reading:**
1. [CONVENTIONS.md](../../CONVENTIONS.md) - Project coding standards
2. [Python Style Guide (PEP 8)](https://pep8.org/)
3. Review [api/v1/documents.py](../../app/api/v1/documents.py) - Example endpoint

**Exercise 3: Code Review Practice**
```python
# Find issues in this code (intentionally bad):

def process_doc(doc_id):  # ❌ Multiple issues
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc == None:
        return None

    result = ocr_service.process(doc.file_path)
    return result

# Issues to identify:
# 1. Missing type hints
# 2. Blocking database call (not async)
# 3. No error handling
# 4. Magic string queries
# 5. No docstring
# 6. Poor variable naming

# Now write it correctly:
async def process_document(document_id: str, db: AsyncSession) -> OCRResult:
    """Process document with OCR engine.

    Args:
        document_id: Unique document identifier
        db: Async database session

    Returns:
        OCR processing result with extracted text

    Raises:
        DocumentNotFoundError: If document doesn't exist
        OCRProcessingError: If OCR fails
    """
    # Get document from database
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    # Process with OCR
    try:
        ocr_result = await ocr_service.process(document.file_path)
        return ocr_result
    except Exception as e:
        logger.exception(f"OCR processing failed for {document_id}")
        raise OCRProcessingError(f"Failed to process {document_id}") from e
```

**Afternoon: Testing Standards (2 hours)**

**Reading:**
1. [Testing Guide](../../Static_Knowledge/Processes/testing_strategy.md)
2. Review [tests/unit/api/test_documents.py](../../tests/unit/api/test_documents.py)

**Exercise 4: Write Tests**
```python
# Write tests for the German text validator

import pytest
from app.utils.german_validator import GermanValidator

class TestGermanValidator:
    @pytest.fixture
    def validator(self):
        """Provide validator instance."""
        return GermanValidator()

    def test_valid_german_text(self, validator):
        """Valid German text should pass validation."""
        text = "Müller GmbH, Königstraße 42, 80539 München"
        assert validator.validate(text) == True

    def test_umlaut_handling(self, validator):
        """Umlauts should be correctly validated."""
        cases = [
            "Größe",  # ß
            "Müller",  # ü
            "Bär",  # ä
            "Löwe",  # ö
        ]
        for text in cases:
            assert validator.validate_umlauts(text), f"Failed on: {text}"

    def test_invalid_encoding(self, validator):
        """Incorrectly encoded German should fail."""
        # Simulated mojibake (encoding issue)
        text = "M\u00fcller"  # Incorrect representation
        assert validator.validate(text) == False

# Run tests
# pytest tests/unit/utils/test_german_validator.py -v
```

**✅ Day 3 Checklist:**
- [ ] Understand type hint requirements
- [ ] Can identify code quality issues
- [ ] Written first unit tests
- [ ] Tests pass with `pytest`

---

### Day 4: Git Workflow & Collaboration (4 hours)

**Morning: Git Best Practices (2 hours)**

**Reading:**
1. [Git Workflow Guide](../../Static_Knowledge/Processes/git_workflow.md)
2. [Conventional Commits](https://www.conventionalcommits.org/)

**Exercise 5: Feature Branch Workflow**
```bash
# Create feature branch
git checkout -b feature/DEV-123-improve-german-validation

# Make changes
# ... edit files ...

# Stage changes
git add app/utils/german_validator.py tests/unit/utils/test_german_validator.py

# Commit with conventional commit format
git commit -m "feat(validation): add enhanced umlaut validation

- Add support for capital ß (ẞ)
- Improve Fraktur character detection
- Add comprehensive test coverage

Closes DEV-123"

# Push to remote
git push origin feature/DEV-123-improve-german-validation

# Create pull request (via GitHub/GitLab interface)
```

**Afternoon: Code Review Process (2 hours)**

**Reading:**
1. [Code Review Checklist](../../Static_Knowledge/Processes/code_review_checklist.md)
2. Review recent merged PRs on GitHub

**Exercise 6: Review Sample PRs**
- Review 3 example pull requests (provided by mentor)
- Leave constructive feedback comments
- Practice using GitHub review tools (approve, request changes, comment)

**Code Review Checklist:**
```markdown
## Functionality
- [ ] Code does what PR description claims
- [ ] Edge cases handled
- [ ] Error handling appropriate

## Code Quality
- [ ] Type hints present and correct
- [ ] Docstrings for public functions
- [ ] No code duplication
- [ ] Follows project conventions

## Testing
- [ ] Tests added for new functionality
- [ ] Tests pass locally
- [ ] Coverage maintained or improved

## Security
- [ ] No secrets in code
- [ ] Input validation present
- [ ] No SQL injection vulnerabilities

## Performance
- [ ] No obvious performance issues
- [ ] Database queries optimized
- [ ] GPU resources managed properly

## German Language
- [ ] User-facing text in German
- [ ] Proper umlaut handling
- [ ] Date/currency formats correct
```

**✅ Day 4 Checklist:**
- [ ] Created feature branch
- [ ] Made commit with conventional format
- [ ] Reviewed 3 example PRs
- [ ] Understand code review process

---

### Day 5: Debugging & Troubleshooting (4 hours)

**Morning: Debugging Tools (2 hours)**

**Tools to Learn:**
1. **Python Debugger (pdb)**
```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or Python 3.7+
breakpoint()

# Common commands:
# n - next line
# s - step into function
# c - continue
# l - list code
# p variable - print variable
# q - quit
```

2. **Docker Logs**
```bash
# View logs
docker-compose logs backend --tail=50
docker-compose logs worker -f  # Follow mode

# Search logs
docker-compose logs | grep ERROR
```

3. **Database Queries**
```sql
-- Check slow queries
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Afternoon: Common Issues Lab (2 hours)**

**Exercise 7: Debug Scenarios**

**Scenario 1: Document Processing Fails**
```bash
# Symptom: Document stuck in "processing" status
# Your task: Find the root cause

# Steps:
# 1. Check worker logs
docker-compose logs worker --tail=100

# 2. Check Celery queue
docker exec ablage-redis redis-cli LLEN celery

# 3. Check GPU status
nvidia-smi

# 4. Check document status in DB
docker exec ablage-postgres psql -U postgres -d ablage \
  -c "SELECT id, status, created_at FROM documents WHERE status='processing';"

# Expected finding: GPU out of memory → solution in gpu_troubleshooting_decision_tree.md
```

**Scenario 2: API Slow Response**
```bash
# Symptom: /api/v1/documents/ endpoint taking >5 seconds
# Your task: Profile and optimize

# Steps:
# 1. Enable query logging
# 2. Check for N+1 queries
# 3. Add database indexes if needed
# 4. Verify improvement

# Reference: performance_degradation_runbook.md
```

**✅ Day 5 Checklist:**
- [ ] Used Python debugger (pdb)
- [ ] Analyzed Docker logs effectively
- [ ] Debugged 2 scenarios successfully
- [ ] Know where to find troubleshooting docs

---

**Week 1 Summary:**
By end of Week 1, you should:
- ✅ Have fully functional development environment
- ✅ Understand system architecture and data flow
- ✅ Know project coding standards and conventions
- ✅ Be able to write code and tests
- ✅ Understand Git workflow and code review process
- ✅ Debug common issues independently

**Week 1 Assessment:**
- [ ] Pass architecture quiz (80% required)
- [ ] Complete development environment setup
- [ ] Submit first practice PR (will be reviewed by mentor)

---

## Week 2: Backend Development

### Day 6: FastAPI Fundamentals (4 hours)

**Morning: FastAPI Basics (2 hours)**

**Reading:**
1. [FastAPI Documentation](https://fastapi.tiangolo.com/)
2. Review [app/api/v1/](../../app/api/v1/) endpoints

**Concepts to Learn:**
- Path parameters and query parameters
- Request/response models (Pydantic)
- Dependency injection
- Async request handlers
- Automatic API documentation

**Exercise 8: Create Simple Endpoint**
```python
# app/api/v1/example.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

router = APIRouter()

@router.get("/documents/{document_id}/metadata")
async def get_document_metadata(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentMetadataResponse:
    """Get document metadata without downloading file.

    Args:
        document_id: Unique document identifier
        db: Database session (injected)
        current_user: Authenticated user (injected)

    Returns:
        Document metadata including size, type, upload date

    Raises:
        HTTPException(404): Document not found
        HTTPException(403): User lacks permission
    """
    # Fetch document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document nicht gefunden")

    # Check permission
    if document.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # Return metadata
    return DocumentMetadataResponse(
        id=document.id,
        filename=document.filename,
        size_bytes=document.file_size_bytes,
        upload_date=document.created_at,
        status=document.status
    )

# Test the endpoint
# curl http://localhost:8000/api/v1/documents/DOC_ID/metadata
```

**Afternoon: Dependency Injection (2 hours)**

**Common Dependencies:**
```python
# Database session
async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

# Current user (authentication)
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    user = await auth_service.verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Ungültiger Token")
    return user

# Permission check
def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin-Rechte erforderlich")
    return current_user

# Rate limiting
async def rate_limit(request: Request):
    client_ip = request.client.host
    requests_count = await redis.incr(f"rate_limit:{client_ip}")
    await redis.expire(f"rate_limit:{client_ip}", 60)

    if requests_count > 100:  # 100 requests per minute
        raise HTTPException(status_code=429, detail="Zu viele Anfragen")
```

**✅ Day 6 Checklist:**
- [ ] Created custom endpoint
- [ ] Used dependency injection
- [ ] Tested endpoint with curl/Postman
- [ ] API docs generated automatically

---

### Day 7: Database Operations (SQLAlchemy) (4 hours)

**Morning: Async SQLAlchemy (2 hours)**

**Reading:**
1. [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
2. Review [app/db/models.py](../../app/db/models.py)

**Database Patterns:**
```python
# ✅ CORRECT: Async queries
async def get_user_documents(user_id: str, db: AsyncSession) -> List[Document]:
    """Get all documents for a user (async)."""
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == user_id)
        .order_by(Document.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()

# ❌ WRONG: Blocking queries
def get_user_documents_blocking(user_id: str, db: Session):
    return db.query(Document).filter(Document.owner_id == user_id).all()

# ✅ CORRECT: Efficient joins
async def get_documents_with_owner(db: AsyncSession):
    """Get documents with owner info (single query)."""
    result = await db.execute(
        select(Document, User)
        .join(User, Document.owner_id == User.id)
        .limit(100)
    )
    return result.all()

# ❌ WRONG: N+1 queries
async def get_documents_with_owner_n_plus_1(db: AsyncSession):
    """N+1 query antipattern (slow)."""
    documents = await db.execute(select(Document).limit(100))

    # Separate query for each document's owner (100 extra queries!)
    for doc in documents:
        owner = await db.execute(select(User).where(User.id == doc.owner_id))
```

**Afternoon: Transactions & Error Handling (2 hours)**

**Exercise 9: Implement Transaction**
```python
async def process_document_with_transaction(
    document_id: str,
    db: AsyncSession
) -> ProcessingResult:
    """Process document with transactional integrity."""
    try:
        # Start transaction (implicit with async_session)
        async with db.begin():
            # Update document status
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="processing")
            )

            # Create processing record
            processing_record = ProcessingRecord(
                document_id=document_id,
                started_at=datetime.utcnow()
            )
            db.add(processing_record)

            # Commit happens automatically if no exception

    except Exception as e:
        # Rollback happens automatically on exception
        logger.exception(f"Processing failed for {document_id}")
        raise
```

**✅ Day 7 Checklist:**
- [ ] Written async database queries
- [ ] Avoided N+1 query antipattern
- [ ] Implemented transaction correctly
- [ ] Tested with real database

---

### Day 8: Celery Background Tasks (4 hours)

**Morning: Celery Basics (2 hours)**

**Reading:**
1. [Celery Documentation](https://docs.celeryq.dev/)
2. Review [app/workers/ocr_tasks.py](../../app/workers/ocr_tasks.py)

**Task Creation:**
```python
# app/workers/ocr_tasks.py
from celery import Task
import torch

@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, document_id: str) -> dict:
    """Celery task for document processing.

    Args:
        self: Task instance (bound)
        document_id: Document to process

    Returns:
        Processing result dict
    """
    try:
        # Load document
        document = load_document_from_minio(document_id)

        # Process with GPU
        with gpu_memory_guard():
            result = ocr_service.process(document)

        # Save results
        save_ocr_result(document_id, result)

        return {"status": "success", "text_length": len(result.text)}

    except torch.cuda.OutOfMemoryError as e:
        # Retry with smaller batch
        logger.warning(f"GPU OOM, retrying with smaller batch: {e}")
        raise self.retry(exc=e, countdown=60)

    except Exception as e:
        logger.exception(f"Task failed for {document_id}")
        raise

# Trigger task from API
@router.post("/documents/{document_id}/process")
async def trigger_processing(document_id: str):
    """Queue document for processing."""
    task = process_document_task.delay(document_id)
    return {"task_id": task.id, "status": "queued"}
```

**Afternoon: Task Monitoring (2 hours)**

**Exercise 10: Task Status Tracking**
```python
# Check task status
@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get status of background task."""
    task = celery_app.AsyncResult(task_id)

    return {
        "task_id": task_id,
        "status": task.status,  # PENDING, STARTED, SUCCESS, FAILURE
        "result": task.result if task.successful() else None,
        "error": str(task.info) if task.failed() else None
    }

# Monitor queue depth
@router.get("/queue/status")
async def queue_status():
    """Get current queue statistics."""
    queue_length = redis.llen("celery")
    active_tasks = celery_app.control.inspect().active()

    return {
        "queued": queue_length,
        "active": len(active_tasks) if active_tasks else 0
    }
```

**✅ Day 8 Checklist:**
- [ ] Created Celery task
- [ ] Triggered task from API
- [ ] Monitored task status
- [ ] Understand retry mechanism

---

### Day 9: German Language Processing (4 hours)

**Morning: German Validation (2 hours)**

**Reading:**
1. [German Language Requirements](../../Static_Knowledge/Technical_Details/german_language_processing.md)
2. Review [app/utils/german_validator.py](../../app/utils/german_validator.py)

**Umlaut Handling:**
```python
import unicodedata

def validate_german_umlauts(text: str) -> bool:
    """Ensure umlauts are correctly encoded."""
    # Normalize to NFC (composed form)
    normalized = unicodedata.normalize('NFC', text)

    # German umlaut characters
    umlauts = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß', 'ẞ']

    # Check if any umlauts present
    has_umlauts = any(char in normalized for char in umlauts)

    # Verify correct encoding (no mojibake)
    try:
        normalized.encode('utf-8').decode('utf-8')
        return True
    except UnicodeError:
        return False

# Test cases
assert validate_german_umlauts("Müller GmbH") == True
assert validate_german_umlauts("M\u00fcller") == True  # Composed ü
assert validate_german_umlauts("Größe") == True  # ß
```

**Afternoon: German Date/Currency Formatting (2 hours)**

**Exercise 11: Format German Business Data**
```python
from datetime import datetime
from decimal import Decimal
import locale

# Set German locale
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

def format_german_date(date: datetime) -> str:
    """Format date in German format: DD.MM.YYYY"""
    return date.strftime("%d.%m.%Y")

def format_german_currency(amount: Decimal) -> str:
    """Format currency in German format: 1.234,56 €"""
    # Format with thousands separator and 2 decimals
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"

def format_german_number(number: float) -> str:
    """Format number in German format: 1.234,56"""
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted

# Test
assert format_german_date(datetime(2025, 1, 23)) == "23.01.2025"
assert format_german_currency(Decimal("1234.56")) == "1.234,56 €"
assert format_german_number(1234.56) == "1.234,56"
```

**✅ Day 9 Checklist:**
- [ ] Understand umlaut encoding (UTF-8, NFC)
- [ ] Implemented German validation
- [ ] Formatted dates/currency correctly
- [ ] All German test cases pass

---

### Day 10: Week 2 Mini-Project (4 hours)

**Project: Implement Document Search Feature**

**Requirements:**
1. Add search endpoint `/api/v1/documents/search`
2. Support German full-text search
3. Filter by date range, document type
4. Paginate results
5. Write comprehensive tests
6. Create pull request

**Implementation Steps:**
```python
# 1. Add database index for full-text search
CREATE INDEX idx_documents_text_search
ON documents USING GIN (to_tsvector('german', extracted_text));

# 2. Implement search endpoint
@router.get("/documents/search")
async def search_documents(
    query: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    document_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentSearchResponse:
    """Search documents with German full-text search."""
    # ... implementation ...

# 3. Write tests
# ... test cases ...

# 4. Create PR and request review from mentor
```

**✅ Week 2 Checklist:**
- [ ] Completed mini-project
- [ ] All tests pass
- [ ] PR created and reviewed
- [ ] Comfortable with backend development

---

## Week 3: Advanced Topics

### Days 11-12: GPU Programming (8 hours)

**Topics:**
- GPU memory management
- Batch processing optimization
- Handling OOM errors
- GPU profiling and monitoring

**Reference:** [GPU Memory Optimization Experiment](../../Dynamic_Knowledge/Experiments/gpu_memory_optimization_experiment.yaml)

---

### Days 13-14: Security & GDPR (8 hours)

**Topics:**
- Authentication and authorization
- GDPR compliance requirements (Art. 5, 15, 17, 30)
- Data protection by design
- Security best practices

**Reference:** [GDPR Compliance Implementation](../../Dynamic_Knowledge/Compliance/gdpr_compliance_implementation.md)

---

### Day 15: Week 3 Review (4 hours)

- Review advanced topics
- Take technical assessment
- Discuss career development

---

## Week 4: Real Project Work

### Days 16-20: Assigned Project (20 hours)

Work on a real feature or bug fix from the backlog, with mentor guidance.

**Project Examples:**
1. Implement new OCR backend integration
2. Add dashboard analytics feature
3. Optimize database query performance
4. Improve error handling in worker tasks

---

## Final Assessment

### Knowledge Check (Week 4, Friday)

**Written Exam (60 minutes):**
- System architecture questions (25%)
- Code quality and best practices (25%)
- Debugging scenarios (25%)
- German language requirements (15%)
- Security and GDPR (10%)

**Passing Score:** 80%

**Practical Coding Exercise (90 minutes):**
- Implement feature from specification
- Write tests
- Create pull request
- Code review with team

---

## Certification

Upon successful completion:
- [ ] Certificate of completion
- [ ] Full commit access to repository
- [ ] Added to on-call rotation (optional)
- [ ] Assigned as PR reviewer

---

## Resources

### Essential Reading
1. [CLAUDE.md](../../CLAUDE.md) - Project context
2. [GETTING_STARTED.md](../../GETTING_STARTED.md) - Quick start
3. [System Architecture](../../Static_Knowledge/Architecture_Decisions/system_architecture.md)
4. [Daily Operations Checklist](../Runbooks/daily_operations_checklist.md)

### External Resources
1. [FastAPI Documentation](https://fastapi.tiangolo.com/)
2. [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/en/20/)
3. [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
4. [PyTorch GPU Guide](https://pytorch.org/docs/stable/notes/cuda.html)

### Internal Contacts
- **Mentor:** [Assigned during Week 1]
- **Team Lead:** [Name]
- **DevOps Contact:** [Name]
- **Security Contact:** [Name]

---

## Feedback & Improvement

This curriculum is continuously improved. Please provide feedback:
- What worked well?
- What was confusing?
- What topics need more/less time?
- Suggestions for improvement?

**Feedback Form:** [internal-link]

---

## Revision History

| Version | Date       | Author        | Changes                         |
|---------|------------|---------------|---------------------------------|
| 1.0     | 2025-01-23 | Engineering Team | Initial developer curriculum |

---

Welcome to the team! 🚀
