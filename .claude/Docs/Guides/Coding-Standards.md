# Coding Standards

## Python Style Guide (PEP 8 + Project Enhancements)

### Type Hints (MANDATORY)

```python
# CORRECT: Full type annotations
from typing import Optional, List, Dict
import asyncio

async def process_document(
    document_id: str,
    ocr_backend: str = "deepseek",
    enable_cache: bool = True
) -> Dict[str, any]:
    """Process document with specified OCR backend.

    Args:
        document_id: Unique document identifier
        ocr_backend: OCR engine to use (deepseek, got_ocr, surya)
        enable_cache: Whether to cache results

    Returns:
        Dictionary with extracted text and metadata

    Raises:
        DocumentNotFoundError: If document doesn't exist
        OCRProcessingError: If OCR fails
    """
    pass

# WRONG: Missing type hints
async def process_document(document_id, ocr_backend="deepseek"):
    pass
```

### Async/Await Pattern

```python
# CORRECT: Async throughout stack
async def get_document(db: AsyncSession, doc_id: str) -> Optional[Document]:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()

# WRONG: Blocking database calls in async function
def get_document(db: Session, doc_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.id == doc_id).first()
```

### Error Handling

```python
# CORRECT: Specific exceptions with context
from app.core.exceptions import OCRProcessingError, GPUOutOfMemoryError

try:
    result = await ocr_service.process(image)
except torch.cuda.OutOfMemoryError as e:
    logger.error(f"GPU OOM processing document {doc_id}", exc_info=True)
    raise GPUOutOfMemoryError(f"Insufficient GPU memory for {doc_id}") from e
except Exception as e:
    logger.exception(f"Unexpected error processing {doc_id}")
    raise OCRProcessingError(f"Failed to process {doc_id}") from e

# WRONG: Bare except or generic exceptions
try:
    result = ocr_service.process(image)
except:
    print("Error occurred")
```

### Logging Standards

```python
import structlog

logger = structlog.get_logger(__name__)

# CORRECT: Structured logging with context
logger.info(
    "ocr_processing_started",
    document_id=doc_id,
    backend=backend_name,
    file_size_mb=file_size / 1024 / 1024,
    gpu_available=torch.cuda.is_available()
)

# WRONG: String concatenation or f-strings in logs
logger.info(f"Processing document {doc_id} with {backend_name}")
```

### Dependency Injection (FastAPI)

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# CORRECT: Dependency injection
async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

@router.post("/documents/")
async def create_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    pass

# WRONG: Global database connections
db = create_database_connection()  # Don't do this
```

### Code Style Rules

| Rule | Value |
|------|-------|
| Line Length | Max 100 characters |
| Indentation | 4 spaces (never tabs) |
| Imports | Organized with Ruff (stdlib, third-party, local) |
| Docstrings | Google style for all public functions/classes |
| String Quotes | Double quotes " preferred |

### German Language Code Comments

```python
# ACCEPTABLE: Technical terms in English, explanations in German
def extract_text_from_image(image: np.ndarray) -> str:
    """Extrahiert Text aus Bild mit OCR.

    Verwendet GPU-beschleunigtes OCR fuer deutsche Dokumente,
    inklusive Frakturschrift-Unterstuetzung.
    """
    # Preprocessing: Bild normalisieren und entrauschen
    preprocessed = preprocess_for_german_ocr(image)

    # OCR mit DeepSeek fuer beste Genauigkeit bei deutschen Texten
    text = deepseek_ocr.extract(preprocessed, language="de")
    return text
```

### File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Python modules | snake_case | `document_service.py` |
| Classes | PascalCase | `DocumentService` |
| Functions/variables | snake_case | `process_document` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| Test files | test_*.py | `test_ocr_service.py` |
| Type stubs | *.pyi | `types.pyi` |
