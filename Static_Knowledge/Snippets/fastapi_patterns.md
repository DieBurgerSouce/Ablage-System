# FastAPI Patterns - Reusable Code Snippets
## OCR Processing, Batch Operations, Error Handling

---

## 1. OCR Processing Endpoint Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.ocr_service import OCRService
from app.core.monitoring import monitor_performance

router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])

@router.post("/process/{document_id}", status_code=status.HTTP_202_ACCEPTED)
@monitor_performance("ocr_process")
async def process_document(
    document_id: str,
    backend: str = "auto",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process document with OCR.

    - **document_id**: Unique document identifier
    - **backend**: OCR engine ('auto', 'deepseek', 'got_ocr', 'surya')

    Returns task ID for async processing status check.
    """
    # Verify document exists and user has access
    document = await document_service.get(db, document_id)
    if not document:
        raise HTTPException(404, "Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(403, "Zugriff verweigert")

    # Queue OCR processing task
    task = await ocr_service.queue_processing(
        document_id=document_id,
        backend=backend,
        user_id=current_user.id
    )

    # Add background cleanup task
    background_tasks.add_task(
        cleanup_temp_files,
        document_id=document_id
    )

    return {
        "status": "queued",
        "task_id": task.id,
        "document_id": document_id,
        "estimated_completion": task.eta
    }
```

---

## 2. Batch Processing Pattern

```python
from typing import List
from pydantic import BaseModel, Field

class BatchProcessRequest(BaseModel):
    document_ids: List[str] = Field(..., max_length=100)
    backend: str = "auto"
    priority: int = Field(default=5, ge=1, le=10)

@router.post("/batch/process", status_code=status.HTTP_202_ACCEPTED)
async def batch_process_documents(
    request: BatchProcessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process multiple documents in batch.

    Automatically groups by backend for optimal GPU utilization.
    """
    # Validate all documents exist and user has access
    documents = []
    for doc_id in request.document_ids:
        doc = await document_service.get(db, doc_id)
        if not doc or doc.owner_id != current_user.id:
            raise HTTPException(
                403,
                f"Zugriff auf Dokument {doc_id} verweigert"
            )
        documents.append(doc)

    # Group by recommended backend
    from collections import defaultdict
    docs_by_backend = defaultdict(list)

    ocr = OCRService()
    for doc in documents:
        backend = await ocr.select_backend(doc) if request.backend == "auto" else request.backend
        docs_by_backend[backend].append(doc.id)

    # Queue batch tasks
    batch_tasks = []
    for backend, doc_ids in docs_by_backend.items():
        task = await ocr_service.queue_batch(
            document_ids=doc_ids,
            backend=backend,
            priority=request.priority
        )
        batch_tasks.append(task)

    return {
        "status": "queued",
        "batch_id": str(uuid.uuid4()),
        "total_documents": len(request.document_ids),
        "tasks": [
            {
                "task_id": task.id,
                "backend": task.backend,
                "document_count": task.document_count
            }
            for task in batch_tasks
        ]
    }
```

---

## 3. Error Handling Pattern with German Messages

```python
from app.core.exceptions import (
    OCRProcessingError,
    GPUOutOfMemoryError,
    DocumentNotFoundError,
    ValidationError
)
import structlog

logger = structlog.get_logger(__name__)

@router.post("/process/{document_id}")
async def process_with_error_handling(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """OCR processing with comprehensive error handling."""
    try:
        result = await ocr_service.process(db, document_id)
        return result

    except DocumentNotFoundError as e:
        logger.warning("document_not_found", document_id=document_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error": "document_not_found",
                "message": "Dokument nicht gefunden",
                "document_id": document_id
            }
        )

    except GPUOutOfMemoryError as e:
        logger.error(
            "gpu_oom",
            document_id=document_id,
            exc_info=True
        )
        # Try CPU fallback
        try:
            result = await ocr_service.process(
                db,
                document_id,
                backend="surya",
                use_gpu=False
            )
            result.metadata['fallback_used'] = True
            return result
        except Exception as fallback_error:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "processing_failed",
                    "message": "Verarbeitung fehlgeschlagen (GPU und CPU)",
                    "document_id": document_id
                }
            )

    except ValidationError as e:
        logger.warning("validation_error", document_id=document_id, errors=e.errors)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_failed",
                "message": "Validierung fehlgeschlagen",
                "errors": e.errors
            }
        )

    except OCRProcessingError as e:
        logger.exception("ocr_processing_error", document_id=document_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "processing_error",
                "message": "OCR-Verarbeitung fehlgeschlagen",
                "document_id": document_id
            }
        )

    except Exception as e:
        logger.exception("unexpected_error", document_id=document_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_server_error",
                "message": "Interner Serverfehler"
            }
        )
```

---

## 4. Health Check Pattern with GPU Monitoring

```python
from app.gpu_manager import GPUManager
from app.core.monitoring import SystemMonitor

@router.get("/health", tags=["Health"])
async def comprehensive_health_check(db: AsyncSession = Depends(get_db)):
    """
    Comprehensive system health check.

    Returns 200 if all systems healthy, 503 otherwise.
    """
    gpu = GPUManager()
    monitor = SystemMonitor()

    checks = {
        "database": await check_database(db),
        "redis": await monitor.check_redis(),
        "minio": await monitor.check_minio(),
        "gpu": gpu.check_availability(),
        "disk_space": monitor.check_disk_space(),
        "celery_workers": await monitor.check_celery_workers()
    }

    # GPU details if available
    if checks["gpu"]["available"]:
        memory_info = gpu.get_memory_info()
        checks["gpu"].update({
            "vram_used_gb": memory_info['used_gb'],
            "vram_free_gb": memory_info['free_gb'],
            "utilization_percent": memory_info['utilization_percent']
        })

    all_healthy = all(check.get('healthy', False) for check in checks.values())

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

async def check_database(db: AsyncSession) -> dict:
    """Check database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"healthy": True}
    except Exception as e:
        return {"healthy": False, "error": str(e)}
```

---

## 5. Dependency Injection Pattern

```python
from fastapi import Depends
from typing import Annotated
from app.services.ocr_service import OCRService
from app.services.document_service import DocumentService
from app.gpu_manager import GPUManager

# Dependency factories
def get_ocr_service() -> OCRService:
    """OCR service dependency."""
    return OCRService()

def get_document_service() -> DocumentService:
    """Document service dependency."""
    return DocumentService()

def get_gpu_manager() -> GPUManager:
    """GPU manager dependency (singleton)."""
    return GPUManager()

# Type aliases for cleaner code
OCRServiceDep = Annotated[OCRService, Depends(get_ocr_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
GPUManagerDep = Annotated[GPUManager, Depends(get_gpu_manager)]
DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

# Usage in endpoint
@router.post("/process/{document_id}")
async def process_document(
    document_id: str,
    ocr: OCRServiceDep,
    docs: DocumentServiceDep,
    gpu: GPUManagerDep,
    db: DatabaseDep
):
    """Endpoint with clean dependency injection."""
    # Check GPU availability
    if not gpu.is_available():
        raise HTTPException(503, "GPU nicht verfügbar")

    # Get document
    document = await docs.get(db, document_id)
    if not document:
        raise HTTPException(404, "Dokument nicht gefunden")

    # Process
    result = await ocr.process(db, document_id)
    return result
```

---

## 6. Request Validation Pattern with Pydantic

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

class DocumentUploadRequest(BaseModel):
    """Document upload request with validation."""

    filename: str = Field(..., max_length=255, min_length=1)
    language: str = Field(default="de", pattern="^(de|en)$")
    document_type: Optional[str] = Field(None, pattern="^(rechnung|vertrag|lieferschein)$")
    metadata: Optional[dict] = None

    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename for security."""
        # Prevent path traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Ungültiger Dateiname (Pfad-Traversierung erkannt)")

        # Check allowed extensions
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff']
        if not any(v.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError(
                f"Dateityp nicht erlaubt. Erlaubt: {', '.join(allowed_extensions)}"
            )

        return v

    @validator('metadata')
    def validate_metadata(cls, v):
        """Ensure metadata doesn't contain sensitive keys."""
        if v:
            sensitive_keys = ['password', 'api_key', 'secret', 'token']
            for key in sensitive_keys:
                if key.lower() in str(v).lower():
                    raise ValueError("Metadata enthält sensible Informationen")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "rechnung_2024_001.pdf",
                "language": "de",
                "document_type": "rechnung",
                "metadata": {"year": 2024, "month": 1}
            }
        }
```

---

## 7. WebSocket Progress Updates Pattern

```python
from fastapi import WebSocket, WebSocketDisconnect
from app.workers.celery_app import celery_app

@router.websocket("/ws/progress/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time OCR progress updates.

    Connect to: ws://localhost:8000/api/v1/ocr/ws/progress/{task_id}
    """
    await websocket.accept()

    try:
        while True:
            # Get task status from Celery
            task = celery_app.AsyncResult(task_id)

            progress_data = {
                "task_id": task_id,
                "state": task.state,
                "progress": task.info.get('progress', 0) if task.info else 0,
                "status": task.info.get('status', '') if task.info else '',
                "timestamp": datetime.utcnow().isoformat()
            }

            # Send progress update
            await websocket.send_json(progress_data)

            # If task complete or failed, close connection
            if task.state in ['SUCCESS', 'FAILURE']:
                if task.state == 'SUCCESS':
                    await websocket.send_json({
                        "task_id": task_id,
                        "state": "SUCCESS",
                        "result": task.result
                    })
                else:
                    await websocket.send_json({
                        "task_id": task_id,
                        "state": "FAILURE",
                        "error": str(task.info)
                    })
                break

            # Wait before next update
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", task_id=task_id)
    finally:
        await websocket.close()
```

---

## 8. GDPR Compliance Logging Pattern

```python
from app.core.gdpr import GDPRLogger

@router.delete("/documents/{document_id}")
async def delete_document_gdpr_compliant(
    document_id: str,
    reason: str,
    db: DatabaseDep,
    current_user: User = Depends(get_current_user)
):
    """
    Delete document with GDPR Article 17 compliance logging.
    """
    gdpr_logger = GDPRLogger()

    # Get document before deletion
    document = await document_service.get(db, document_id)
    if not document:
        raise HTTPException(404, "Dokument nicht gefunden")

    # Verify access
    if document.owner_id != current_user.id:
        raise HTTPException(403, "Zugriff verweigert")

    # Log GDPR deletion (Art. 17)
    await gdpr_logger.log_deletion(
        data_type="document",
        data_id=document_id,
        user_id=current_user.id,
        reason=reason,
        legal_basis="Art. 17 DSGVO (Recht auf Löschung)"
    )

    # Perform deletion
    await document_service.delete(db, document_id)

    # Delete from storage
    await storage_service.delete_file(document.file_path)

    # Clear cache
    await cache_service.delete(f"doc:{document_id}")

    return {
        "status": "deleted",
        "document_id": document_id,
        "timestamp": datetime.utcnow().isoformat(),
        "gdpr_logged": True
    }
```

---

## Best Practices Summary

1. **Always use type hints** - Enable mypy strict mode
2. **Validate inputs with Pydantic** - Prevent security issues
3. **Handle errors gracefully** - German error messages for users
4. **Log with structured logging** - Use structlog for context
5. **Use dependency injection** - Keep endpoints clean and testable
6. **Monitor performance** - Decorator pattern for metrics
7. **Implement GDPR logging** - Track all data operations
8. **Provide WebSocket updates** - Real-time progress for long tasks

---

## References

- [app/main.py](../../app/main.py) - Main FastAPI application
- [app/api/v1/](../../app/api/v1/) - API endpoints
- [app/core/exceptions.py](../../app/core/exceptions.py) - Custom exceptions
- [CLAUDE.md](../../CLAUDE.md) - Full project context
