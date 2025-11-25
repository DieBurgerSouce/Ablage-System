"""
Example Usage - Sentry Integration
Demonstrates how to use Sentry in Ablage-System
"""

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.sentry.init_sentry import initialize_sentry_for_backend
from infrastructure.sentry.middleware import SentryMiddleware, SentryContextMiddleware
from infrastructure.sentry.sentry import (
    set_user_context,
    set_context,
    add_breadcrumb,
    capture_exception,
    capture_message,
    trace_function,
    trace_span,
    SentryTransaction,
    track_gpu_operation,
)


# ============================================
# Example 1: FastAPI Application Setup
# ============================================

app = FastAPI(title="Ablage-System OCR")

# Initialize Sentry on startup
@app.on_event("startup")
async def startup_event():
    """Initialize Sentry when application starts."""
    initialize_sentry_for_backend(
        app_name="ablage-backend",
        environment="production",
        release="0.1.0"
    )

# Add Sentry middleware
app.add_middleware(SentryMiddleware, slow_request_threshold_ms=1000)
app.add_middleware(SentryContextMiddleware)


# ============================================
# Example 2: API Endpoints with User Context
# ============================================

@app.get("/api/v1/documents/{document_id}")
async def get_document(
    document_id: str,
    current_user = Depends(get_current_user),  # Your auth dependency
    db: AsyncSession = Depends(get_db)
):
    """Get document with Sentry tracking."""

    # Set user context for error tracking
    set_user_context(
        user_id=str(current_user.id),
        email=current_user.email,
        username=current_user.username
    )

    # Add breadcrumb for debugging
    add_breadcrumb(
        message=f'Fetching document {document_id}',
        category='api',
        level='info',
        data={'document_id': document_id}
    )

    try:
        document = await fetch_document_from_db(db, document_id)

        if not document:
            # This will be tracked as a 404 in Sentry
            raise HTTPException(status_code=404, detail="Document not found")

        return document

    except Exception as e:
        # Capture exception with extra context
        capture_exception(e, extra={
            'document_id': document_id,
            'user_id': current_user.id,
        })
        raise


# ============================================
# Example 3: Performance Tracking with Decorators
# ============================================

@trace_function(op='ocr.process')
async def process_document_with_ocr(document_id: str, backend: str = 'deepseek'):
    """Process document with OCR - tracked by Sentry."""

    # Add custom context
    set_context('ocr', {
        'backend': backend,
        'document_id': document_id,
        'language': 'de',
    })

    # This function's execution time will be tracked
    result = await ocr_service.process(document_id, backend)

    return result


@trace_span(op='db.query', description='Fetch documents from database')
async def fetch_document_from_db(db: AsyncSession, document_id: str):
    """Database query with span tracking."""
    # This span will appear under the parent transaction
    result = await db.execute(...)
    return result.scalar_one_or_none()


# ============================================
# Example 4: Manual Transaction Creation
# ============================================

async def batch_process_documents(document_ids: list[str]):
    """Batch process documents with custom transaction."""

    with SentryTransaction('batch_process', op='ocr.batch') as transaction:
        # Set transaction tags
        transaction.set_tag('batch_size', len(document_ids))
        transaction.set_tag('backend', 'deepseek')

        # Set transaction data
        transaction.set_data('document_ids', document_ids)

        try:
            results = []
            for doc_id in document_ids:
                result = await process_document_with_ocr(doc_id)
                results.append(result)

            # Mark as successful
            transaction.set_status('ok')
            return results

        except Exception as e:
            # Mark as failed
            transaction.set_status('internal_error')
            capture_exception(e)
            raise


# ============================================
# Example 5: GPU Operations Tracking
# ============================================

async def process_with_deepseek(image_path: str):
    """Process image with DeepSeek - track GPU usage."""

    with track_gpu_operation('inference', 'deepseek'):
        # GPU operation is tracked
        try:
            import torch

            # Add GPU context
            if torch.cuda.is_available():
                set_context('gpu', {
                    'device': torch.cuda.get_device_name(0),
                    'memory_allocated': torch.cuda.memory_allocated(),
                    'memory_cached': torch.cuda.memory_reserved(),
                })

            # Process image
            result = deepseek_model.process(image_path)

            return result

        except torch.cuda.OutOfMemoryError as e:
            # GPU OOM error - will be tagged and tracked
            capture_exception(e, extra={
                'image_path': image_path,
                'gpu_memory': torch.cuda.memory_allocated(),
            })
            raise


# ============================================
# Example 6: Celery Worker Integration
# ============================================

from celery import Celery
from infrastructure.sentry.init_sentry import initialize_sentry_for_worker
from infrastructure.sentry.celery_integration import (
    SentryTask,
    track_ocr_task,
    track_database_operation,
)

# Initialize Celery
celery_app = Celery('ablage-worker')

# Initialize Sentry for worker
@celery_app.on_after_configure.connect
def setup_sentry(sender, **kwargs):
    """Initialize Sentry when Celery worker starts."""
    initialize_sentry_for_worker(
        worker_name="ablage-worker",
        environment="production",
        release="0.1.0"
    )


# OCR task with Sentry tracking
@track_ocr_task(backend='deepseek')
@celery_app.task(base=SentryTask, bind=True, max_retries=3)
def process_document_task(self, document_id: str, backend: str = 'deepseek'):
    """Celery task for document processing - tracked by Sentry."""

    try:
        # Add context
        set_context('task', {
            'document_id': document_id,
            'backend': backend,
            'retry_count': self.request.retries,
        })

        # Process document
        result = process_document_sync(document_id, backend)

        return result

    except Exception as e:
        # Capture exception and retry
        capture_exception(e, extra={
            'document_id': document_id,
            'backend': backend,
            'task_id': self.request.id,
        })

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# ============================================
# Example 7: Custom Error Handling
# ============================================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Custom error handler - capture in Sentry."""

    # Capture error with request context
    capture_exception(exc, extra={
        'url': str(request.url),
        'method': request.method,
        'client': request.client.host if request.client else None,
    })

    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


# ============================================
# Example 8: Logging Integration
# ============================================

import logging

logger = logging.getLogger(__name__)

async def complex_operation():
    """Example with logging integration."""

    # Info logs are sent as breadcrumbs
    logger.info("Starting complex operation")

    try:
        # Add structured breadcrumb
        add_breadcrumb(
            message='Processing step 1',
            category='operation',
            level='info'
        )

        result = await step_1()

        add_breadcrumb(
            message='Processing step 2',
            category='operation',
            level='info'
        )

        result = await step_2(result)

        logger.info("Complex operation completed successfully")
        return result

    except Exception as e:
        # Error logs are sent as events
        logger.error(f"Complex operation failed: {e}")

        # Manually capture with extra context
        capture_exception(e, extra={
            'operation': 'complex_operation',
            'step': 'unknown',
        })
        raise


# ============================================
# Example 9: Capturing Custom Messages
# ============================================

async def check_gpu_health():
    """Health check with custom message capture."""

    try:
        import torch

        if not torch.cuda.is_available():
            # Warning level message
            capture_message(
                "GPU not available - using CPU fallback",
                level='warning',
                extra={
                    'cuda_available': False,
                    'device_count': 0,
                }
            )
            return {'status': 'degraded', 'reason': 'no_gpu'}

        # Check GPU memory
        memory_allocated = torch.cuda.memory_allocated()
        memory_total = torch.cuda.get_device_properties(0).total_memory
        usage_percent = (memory_allocated / memory_total) * 100

        if usage_percent > 90:
            # Error level message
            capture_message(
                f"GPU memory usage critical: {usage_percent:.1f}%",
                level='error',
                extra={
                    'memory_allocated': memory_allocated,
                    'memory_total': memory_total,
                    'usage_percent': usage_percent,
                }
            )
            return {'status': 'critical', 'usage': usage_percent}

        return {'status': 'healthy', 'usage': usage_percent}

    except Exception as e:
        capture_exception(e)
        raise


# ============================================
# Example 10: Database Operations Tracking
# ============================================

@track_database_operation('select')
async def get_documents_by_user(db: AsyncSession, user_id: str, limit: int = 20):
    """Get documents with database operation tracking."""

    # This database query will be tracked as a span
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == user_id)
        .limit(limit)
    )

    documents = result.scalars().all()

    # Add breadcrumb with result count
    add_breadcrumb(
        message=f'Retrieved {len(documents)} documents',
        category='database',
        level='info',
        data={
            'user_id': user_id,
            'count': len(documents),
            'limit': limit,
        }
    )

    return documents
