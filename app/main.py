"""
Ablage-System OCR API
Main FastAPI application entry point

Created: 2025-11-22
Status: Working POC with Surya OCR
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path
import structlog
import os
import json

# Use absolute imports for production compatibility
from app.gpu_manager import GPUManager
from app.german_validator import GermanValidator
from app.services.ocr_service import OCRService
from app.core.rate_limiting import (
    limiter,
    rate_limit_exceeded_handler_german,
    get_redis_storage,
    RateLimitTier
)
from app.middleware import RateLimitMiddleware, DevelopmentRateLimitBypass
from app.core.config import settings
from app.core.monitoring import get_system_monitor, PerformanceTimer
from app.core.german_messages import HTTPErrors, StatusMessages

logger = structlog.get_logger(__name__)

# Initialize Sentry (if configured)
try:
    from infrastructure.sentry.init_sentry import initialize_sentry_for_backend
    initialize_sentry_for_backend()
    logger.info("sentry_initialized")
except Exception as e:
    logger.warning("sentry_not_configured", error=str(e))

# Global instances
gpu_manager = None
german_validator = None
ocr_service = None
redis_storage = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global gpu_manager, german_validator, ocr_service, redis_storage

    # Startup
    logger.info("api_starting")

    # Initialize managers
    gpu_manager = GPUManager()
    german_validator = GermanValidator()
    ocr_service = OCRService()

    # Initialize rate limiting Redis storage
    if settings.RATE_LIMIT_ENABLED:
        redis_storage = await get_redis_storage()
        logger.info("rate_limiting_enabled", redis_available=redis_storage.is_available if redis_storage else False)

    logger.info("available_ocr_backends", backends=ocr_service.backend_manager.get_available_backends())
    logger.info("api_started")

    yield

    # Shutdown
    logger.info("api_shutting_down")
    if ocr_service:
        await ocr_service.cleanup()
    if redis_storage:
        await redis_storage.disconnect()
    logger.info("api_shutdown_complete")


# Initialize FastAPI app
app = FastAPI(
    title="Ablage-System OCR",
    description="Enterprise German Document Processing with GPU Acceleration",
    version="0.2.0-poc",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware for web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
if settings.DEBUG:
    # Bypass rate limiting in development
    app.add_middleware(DevelopmentRateLimitBypass)

if settings.RATE_LIMIT_ENABLED:
    # Add rate limiting middleware
    # Note: redis_storage will be set during startup
    app.add_middleware(
        RateLimitMiddleware,
        redis_storage=None  # Will be set during startup
    )

# Register rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler_german)

# Add limiter state to app for SlowAPI decorators
app.state.limiter = limiter

# Include API routers
from app.api.v1 import auth, tasks, metrics, ml, versions, documents
from app.api.v1.admin import router as admin_router
from app.api.v1.backup import router as backup_router

app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(versions.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(backup_router, prefix="/api/v1")


# ==================== Health & Status Endpoints ====================

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Ablage-System OCR",
        "version": "0.2.0-poc",
        "status": "operational",
        "documentation": "/docs",
        "endpoints": {
            "health": "/health",
            "gpu_status": "/gpu/status",
            "ocr_process": "/ocr/process",
            "ocr_test": "/ocr/test",
            "backends": "/ocr/backends"
        },
        "authentication": {
            "register": "/api/v1/auth/register",
            "login": "/api/v1/auth/login",
            "refresh": "/api/v1/auth/refresh",
            "logout": "/api/v1/auth/logout",
            "me": "/api/v1/auth/me"
        },
        "monitoring": {
            "prometheus": "/api/v1/metrics",
            "business_metrics": "/api/v1/metrics/business",
            "system_status": "/monitoring/system",
            "health_check": "/monitoring/health"
        },
        "admin": {
            "users": "/api/v1/admin/users",
            "system": "/api/v1/admin/system/dashboard",
            "jobs": "/api/v1/admin/jobs",
            "rate_limits": "/api/v1/admin/rate-limits",
            "audit": "/api/v1/admin/audit/logs"
        }
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    gpu_status = gpu_manager.get_detailed_status() if gpu_manager else None
    ocr_backends = ocr_service.backend_manager.get_available_backends() if ocr_service else []

    health = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "gpu": {
                "available": gpu_status is not None and gpu_status.get("available", False),
                "device": gpu_status.get("device_name") if gpu_status else None
            },
            "ocr": {
                "backends_available": len(ocr_backends),
                "backends": ocr_backends
            },
            "german_validator": {
                "available": german_validator is not None
            }
        }
    }

    # Determine overall health
    if not ocr_backends:
        health["status"] = "degraded"
        health["message"] = "No OCR backends available"

    return health


# ==================== GPU Management Endpoints ====================

@app.get("/gpu/status")
async def get_gpu_status():
    """Get detailed GPU status"""
    if not gpu_manager:
        raise HTTPException(status_code=503, detail=HTTPErrors.GPU_MANAGER_NOT_INITIALIZED)

    return gpu_manager.get_detailed_status()


# ==================== OCR Processing Endpoints ====================

@app.get("/ocr/backends")
async def get_ocr_backends():
    """Get available OCR backends and their status"""
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    return {
        "available_backends": ocr_service.backend_manager.get_available_backends(),
        "backend_status": await ocr_service.backend_manager.get_backend_status(),
        "recommended": "surya"  # CPU-based, always available
    }


@app.post("/ocr/process")
async def process_document(
    file: UploadFile = File(...),
    backend: Optional[str] = Form("auto"),
    language: Optional[str] = Form("de"),
    detect_layout: Optional[bool] = Form(True)
):
    """
    Process a document with OCR

    Args:
        file: Document file (PDF, PNG, JPG, etc.)
        backend: OCR backend to use (auto, surya, got_ocr, deepseek)
        language: Target language (de, en)
        detect_layout: Whether to detect document layout

    Returns:
        OCR processing result with extracted text
    """
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    # Get system monitor for metrics
    monitor = get_system_monitor()

    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=HTTPErrors.INVALID_FILE_TYPE.format(allowed=", ".join(allowed_extensions))
            )

        # Save uploaded file
        file_content = await file.read()
        saved_path = await ocr_service.save_upload(file_content, file.filename)

        logger.info("processing_document", filename=file.filename, backend=backend, language=language)

        # Process with OCR using performance timer
        with PerformanceTimer("ocr_processing", monitor.metrics) as timer:
            result = await ocr_service.process_document(
                image_path=saved_path,
                backend=backend,
                language=language,
                detect_layout=detect_layout
            )

        # Record metrics
        success = result.get("success", False)
        actual_backend = result.get("backend", backend or "auto")
        monitor.metrics.record_request(
            duration_ms=timer.duration_ms or 0,
            backend=actual_backend,
            success=success
        )

        # Validate German text if language is German
        if language == "de" and result.get("success") and result.get("text"):
            validation = await ocr_service.validate_german_text(result["text"])
            result["german_validation"] = validation

        return result

    except Exception as e:
        logger.error("ocr_processing_failed", error=str(e))
        # Record error metric
        monitor.metrics.record_error("ocr_processing_error")
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


@app.post("/ocr/batch")
async def process_batch(
    files: List[UploadFile] = File(...),
    backend: Optional[str] = Form("auto"),
    language: Optional[str] = Form("de")
):
    """
    Process multiple documents in batch

    Args:
        files: List of document files
        backend: OCR backend to use
        language: Target language

    Returns:
        List of OCR results
    """
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    try:
        # Save all files
        saved_paths = []
        for file in files:
            file_content = await file.read()
            saved_path = await ocr_service.save_upload(file_content, file.filename)
            saved_paths.append(saved_path)

        logger.info("batch_processing", document_count=len(files))

        # Process batch
        results = await ocr_service.batch_process(
            image_paths=saved_paths,
            backend=backend,
            language=language
        )

        return {
            "total": len(files),
            "successful": sum(1 for r in results if r.get("success")),
            "results": results
        }

    except Exception as e:
        logger.error("batch_processing_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


@app.post("/ocr/test")
async def test_german_text(text: str):
    """
    Test German text validation

    Args:
        text: Text to validate

    Returns:
        Validation results with quality metrics
    """
    if not german_validator:
        raise HTTPException(status_code=503, detail=HTTPErrors.GERMAN_VALIDATOR_NOT_INITIALIZED)

    # Validate text
    has_umlauts = german_validator.validate_umlauts(text)
    dates = german_validator.validate_date_format(text)
    amounts = german_validator.validate_currency_format(text)
    business_terms = german_validator.extract_business_terms(text)

    # Check for IBANs and VAT IDs
    ibans = []
    vat_ids = []
    words = text.split()
    for word in words:
        if word.startswith("DE") and len(word) == 22:
            if german_validator.validate_iban(word):
                ibans.append(word)
        elif word.startswith("DE") and len(word) == 11:
            if german_validator.validate_vat_id(word):
                vat_ids.append(word)

    return {
        "valid_german": has_umlauts or len(dates) > 0 or len(amounts) > 0,
        "has_umlauts": has_umlauts,
        "dates": dates,
        "amounts": amounts,
        "business_terms": business_terms,
        "ibans": ibans,
        "vat_ids": vat_ids,
        "text_length": len(text),
        "word_count": len(words)
    }


# ==================== Statistics Endpoint ====================

@app.get("/stats")
async def get_statistics():
    """Get OCR processing statistics"""
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    return await ocr_service.get_stats()


# ==================== System Monitoring Endpoint ====================

@app.get("/monitoring/system")
async def get_system_status():
    """
    Get comprehensive system status including CPU, RAM, GPU, and OCR metrics.

    Returns:
        System resource usage, GPU status, and processing metrics
    """
    monitor = get_system_monitor()
    return {
        "system": monitor.get_system_status(),
        "health": monitor.check_health(),
        "metrics": monitor.metrics.get_summary()
    }


@app.get("/monitoring/health")
async def get_monitoring_health():
    """
    Get system health status for monitoring and alerting.

    Returns:
        Health status of all system components
    """
    monitor = get_system_monitor()
    return monitor.check_health()


# ==================== Rate Limit Status Endpoint ====================

@app.get("/ratelimit/status")
async def get_rate_limit_status():
    """
    Get rate limiting status and statistics.

    Returns:
        Rate limit configuration and statistics
    """
    from app.middleware import get_rate_limit_stats

    return get_rate_limit_stats()


@app.get("/ratelimit/info")
async def get_rate_limit_info_endpoint(request: Request):
    """
    Get rate limit information for current request.

    Returns:
        Current user's rate limit information
    """
    from app.core.rate_limiting import get_rate_limit_info

    return get_rate_limit_info(request)


# ==================== Error Handlers ====================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "fehler": "Nicht gefunden",
            "nachricht": f"Die angeforderte URL {request.url.path} wurde nicht gefunden",
            "zeitstempel": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    logger.error("internal_server_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "fehler": "Interner Serverfehler",
            "nachricht": HTTPErrors.INTERNAL_ERROR,
            "zeitstempel": datetime.now(timezone.utc).isoformat()
        }
    )


# ==================== Main Entry Point ====================

if __name__ == "__main__":
    import uvicorn

    # Configuration
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "true").lower() == "true"

    logger.info("starting_server", host=host, port=port)
    logger.info("api_docs_available", url="http://localhost:8000/docs")

    # Run server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )