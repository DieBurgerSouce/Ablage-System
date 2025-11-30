"""
Ablage-System OCR API
Main FastAPI application entry point

Created: 2025-11-22
Status: Working POC with Surya OCR
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import sys
from pathlib import Path
import structlog
import os
import json

# Magic-byte validation for file upload security
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    magic = None
    MAGIC_AVAILABLE = False

# Use absolute imports for production compatibility
from app.gpu_manager import GPUManager
from app.german_validator import GermanValidator
from app.services.ocr_service import OCRService
from app.core.rate_limiting import (
    limiter,
    rate_limit_exceeded_handler_german,
    get_redis_storage,
    RateLimitTier,
    RateLimitStorageError,
)
from app.middleware import RateLimitMiddleware, DevelopmentRateLimitBypass, SecurityHeadersMiddleware, RequestSizeLimitMiddleware, CSRFMiddleware, get_csrf_token_response, IPBlockingMiddleware
from app.core.config import settings
from app.core.monitoring import get_system_monitor, PerformanceTimer
from app.core.german_messages import HTTPErrors, StatusMessages
from app.services.storage_service import cleanup_storage_service
from app.core.idempotency import check_idempotency, get_idempotency_service
from app.services.ocr_cache_service import get_ocr_cache_service, get_cached_ocr_result, cache_ocr_result

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

# Allowed MIME types mapped to extensions
ALLOWED_MIME_TYPES = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/tiff": [".tif", ".tiff"],
    "image/bmp": [".bmp"],
    "image/gif": [".gif"],
}

# Reverse mapping: extension to expected MIME types
EXTENSION_MIME_MAP = {}
for mime, exts in ALLOWED_MIME_TYPES.items():
    for ext in exts:
        if ext not in EXTENSION_MIME_MAP:
            EXTENSION_MIME_MAP[ext] = []
        EXTENSION_MIME_MAP[ext].append(mime)


def validate_file_content_type(content: bytes, filename: str) -> Tuple[bool, str, str]:
    """
    Validate file content using magic bytes.

    Prevents malicious files being uploaded with spoofed extensions.

    Args:
        content: File content bytes
        filename: Original filename

    Returns:
        Tuple of (is_valid, detected_mime, error_message)
    """
    if not content:
        return False, "", "Leere Datei"

    file_ext = Path(filename).suffix.lower() if filename else ""

    if not MAGIC_AVAILABLE:
        # Fallback: Basic magic byte detection without python-magic
        mime_type = _detect_mime_basic(content)
        if not mime_type:
            # SICHERHEIT: Strenge Validierung - unbekannte Dateien ablehnen
            # Basic magic byte detection fehlgeschlagen = potentiell gefährlicher Dateityp
            logger.error(
                "magic_detection_failed_strict",
                filename=filename,
                message="Dateityp konnte nicht verifiziert werden - Ablehnung aus Sicherheitsgründen"
            )
            return False, "unknown", (
                "Dateityp konnte nicht verifiziert werden. "
                "Bitte installieren Sie python-magic für erweiterte Validierung: "
                "pip install python-magic-bin (Windows) oder python-magic (Linux/Mac)"
            )
    else:
        try:
            mime_type = magic.from_buffer(content, mime=True)
        except Exception as e:
            logger.warning("magic_detection_error", error=str(e), filename=filename)
            # On error, use fallback
            mime_type = _detect_mime_basic(content)

    if not mime_type:
        return False, "", "Dateityp konnte nicht erkannt werden"

    # Check if MIME type is allowed
    if mime_type not in ALLOWED_MIME_TYPES:
        return False, mime_type, f"Dateityp nicht erlaubt: {mime_type}"

    # Check if MIME type matches extension
    expected_mimes = EXTENSION_MIME_MAP.get(file_ext, [])
    if expected_mimes and mime_type not in expected_mimes:
        return False, mime_type, (
            f"Dateiinhalt ({mime_type}) stimmt nicht mit Erweiterung ({file_ext}) überein. "
            f"Möglicher Sicherheitsverstoß."
        )

    return True, mime_type, ""


def _detect_mime_basic(content: bytes) -> Optional[str]:
    """
    Basic MIME type detection using magic bytes (fallback without python-magic).

    Args:
        content: File content bytes

    Returns:
        Detected MIME type or None
    """
    if len(content) < 8:
        return None

    # Magic byte signatures
    signatures = {
        b'%PDF': 'application/pdf',
        b'\xff\xd8\xff': 'image/jpeg',
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'II*\x00': 'image/tiff',  # Little-endian TIFF
        b'MM\x00*': 'image/tiff',  # Big-endian TIFF
        b'BM': 'image/bmp',
        b'GIF87a': 'image/gif',
        b'GIF89a': 'image/gif',
    }

    for sig, mime in signatures.items():
        if content[:len(sig)] == sig:
            return mime

    return None


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
    # Cleanup storage service (MinIO client)
    await cleanup_storage_service()
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

# Request Size Limit Middleware (MUSS als erstes, um DoS zu verhindern)
# Prüft Content-Length Header VOR dem Upload
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_size_bytes=10 * 1024 * 1024,  # 10MB für normale Requests
    upload_max_size_bytes=settings.max_upload_size_bytes,  # 50MB für Uploads (aus config)
)

# IP-Blocking Middleware (blockiert gesperrte IPs aus Incident Response)
# Prüft gegen In-Memory-Liste und Redis
app.add_middleware(
    IPBlockingMiddleware,
    enabled=not settings.DEBUG,  # Nur in Production
    whitelist={"127.0.0.1", "::1", "localhost"},
)

# Add Security Headers middleware (MUSS vor CORS sein!)
# Fügt X-Content-Type-Options, X-Frame-Options, CSP, HSTS, etc. hinzu
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=not settings.DEBUG,  # HSTS nur in Production
    enable_csp=True,
)

# Add CORS middleware for web interface
# WICHTIG: In Production explizite Origins setzen via CORS_ORIGINS Umgebungsvariable!
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=settings.CORS_EXPOSE_HEADERS,
    max_age=settings.CORS_MAX_AGE,
)

# Add CSRF protection middleware
# Double-Submit-Cookie-Pattern für SPA-kompatiblen CSRF-Schutz
# Bei Bearer-Token-Authentifizierung wird CSRF automatisch übersprungen
app.add_middleware(
    CSRFMiddleware,
    enabled=settings.CSRF_ENABLED,
    cookie_secure=not settings.DEBUG,
    cookie_samesite="strict",
    bearer_token_bypass=True,  # API-Clients mit Bearer Token überspringen
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


# Exception handler for rate limit storage errors (fail-closed mode)
@app.exception_handler(RateLimitStorageError)
async def rate_limit_storage_error_handler(request: Request, exc: RateLimitStorageError):
    """
    Handle rate limit storage unavailable errors (fail-closed mode).

    When Redis is unavailable and fail_closed=True, requests are denied
    for security reasons (preventing brute-force during Redis outages).
    """
    logger.error(
        "rate_limit_storage_unavailable",
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
        error=str(exc),
    )
    return JSONResponse(
        status_code=503,
        content={
            "fehler": "Service vorübergehend nicht verfügbar",
            "nachricht": str(exc),
            "zeitstempel": datetime.now(timezone.utc).isoformat(),
            "pfad": request.url.path,
        },
        headers={
            "Retry-After": "60",  # Suggest retry in 1 minute
        },
    )

# Add limiter state to app for SlowAPI decorators
app.state.limiter = limiter

# Include API routers
from app.api.v1 import auth, tasks, metrics, ml, versions, documents, health, ocr
from app.api.v1.admin import router as admin_router
from app.api.v1.backup import router as backup_router
from app.api.v1.vault import router as vault_router
from app.api.v1.gdpr import router as gdpr_router, admin_router as gdpr_admin_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.search import router as search_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.batch_jobs import router as batch_jobs_router

app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(versions.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(backup_router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(ocr.router, prefix="/api/v1")
app.include_router(vault_router, prefix="/api/v1")
app.include_router(gdpr_router, prefix="/api/v1")
app.include_router(gdpr_admin_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(favorites_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(api_keys_router, prefix="/api/v1")
app.include_router(batch_jobs_router, prefix="/api/v1")


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
    request: Request,
    file: UploadFile = File(...),
    backend: Optional[str] = Form("auto"),
    language: Optional[str] = Form("de"),
    detect_layout: Optional[bool] = Form(True),
    cached_response: Optional[Dict[str, Any]] = Depends(check_idempotency)
):
    """
    Process a document with OCR

    Args:
        file: Document file (PDF, PNG, JPG, etc.)
        backend: OCR backend to use (auto, surya, got_ocr, deepseek)
        language: Target language (de, en)
        detect_layout: Whether to detect document layout
        cached_response: Gecachte Antwort bei Idempotency-Key (automatisch geprüft)

    Returns:
        OCR processing result with extracted text

    Headers:
        Idempotency-Key: Optional. Bei Wiederholung wird gecachtes Ergebnis zurückgegeben.
    """
    # Wenn gecachte Antwort vorhanden, direkt zurückgeben
    if cached_response:
        return JSONResponse(
            content=cached_response["response"],
            status_code=cached_response.get("status_code", 200),
            headers={"X-Idempotency-Cached": "true"}
        )
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    # Get system monitor for metrics
    monitor = get_system_monitor()

    try:
        # === INPUT VALIDATION ===

        # 1. Validate file extension
        allowed_extensions = settings.ALLOWED_EXTENSIONS
        file_ext = Path(file.filename).suffix.lower() if file.filename else ""
        if not file_ext or file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=HTTPErrors.INVALID_FILE_TYPE.format(allowed=", ".join(allowed_extensions))
            )

        # 2. Read and validate file size
        file_content = await file.read()
        file_size_mb = len(file_content) / (1024 * 1024)

        if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"Datei zu groß: {file_size_mb:.1f}MB. Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB"
            )

        if len(file_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Leere Datei. Bitte eine gültige Datei hochladen."
            )

        # 2b. Validate file content type (magic bytes) - Security check
        is_valid_content, detected_mime, content_error = validate_file_content_type(
            file_content, file.filename
        )
        if not is_valid_content:
            logger.warning(
                "file_content_validation_failed",
                filename=file.filename,
                detected_mime=detected_mime,
                error=content_error
            )
            raise HTTPException(
                status_code=400,
                detail=content_error or "Ungültiger Dateiinhalt"
            )

        # 2c. Extended security validation (PDF bombs, image bombs)
        from app.core.file_validation import validate_file_security, FileValidationError
        try:
            is_secure, security_error, security_metadata = validate_file_security(
                file_content, file.filename, detected_mime
            )
            if not is_secure:
                logger.warning(
                    "file_security_validation_failed",
                    filename=file.filename,
                    error=security_error,
                    metadata=security_metadata
                )
                raise HTTPException(
                    status_code=400,
                    detail=security_error or "Sicherheitsvalidierung fehlgeschlagen"
                )
        except FileValidationError as e:
            raise HTTPException(status_code=400, detail=e.user_message_de)

        # 2d. Check OCR result cache (based on file hash)
        cached_ocr = await get_cached_ocr_result(
            content=file_content,
            backend=backend or "auto",
            language=language or "de"
        )
        if cached_ocr:
            logger.info(
                "ocr_cache_hit",
                filename=file.filename,
                backend=backend,
            )
            return JSONResponse(
                content=cached_ocr,
                headers={"X-OCR-Cached": "true"}
            )

        # 3. Validate backend parameter
        valid_backends = ["auto", "surya", "got_ocr", "deepseek", "surya_gpu"]
        if backend and backend not in valid_backends:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültiger Backend: {backend}. Erlaubt: {', '.join(valid_backends)}"
            )

        # 4. Validate language parameter
        valid_languages = ["de", "en"]
        if language and language not in valid_languages:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültige Sprache: {language}. Erlaubt: {', '.join(valid_languages)}"
            )

        # 5. Log validated input
        logger.info(
            "input_validation_passed",
            filename=file.filename,
            size_mb=round(file_size_mb, 2),
            backend=backend,
            language=language
        )

        # Save uploaded file
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

        # Cache OCR result for identical file uploads (24h TTL)
        if result.get("success"):
            await cache_ocr_result(
                content=file_content,
                backend=actual_backend,
                result=result,
                language=language or "de"
            )

        # Cache result if Idempotency-Key was provided
        idempotency_key = getattr(request.state, "idempotency_key", None)
        if idempotency_key:
            idempotency_service = get_idempotency_service()
            user_id = getattr(request.state, "idempotency_user_id", None)
            await idempotency_service.cache_response(
                idempotency_key=idempotency_key,
                response_data=result,
                status_code=200,
                user_id=user_id
            )

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
        files: List of document files (max 32 Dateien)
        backend: OCR backend to use
        language: Target language

    Returns:
        List of OCR results
    """
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    # === BATCH VALIDATION ===

    # 1. Validate batch size (max 32 documents as per GPU batch size setting)
    max_batch_size = settings.GPU_BATCH_SIZE
    if len(files) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"Zu viele Dateien: {len(files)}. Maximum pro Batch: {max_batch_size}"
        )

    if len(files) == 0:
        raise HTTPException(
            status_code=400,
            detail="Keine Dateien hochgeladen. Mindestens eine Datei erforderlich."
        )

    # 2. Validate backend parameter
    valid_backends = ["auto", "surya", "got_ocr", "deepseek", "surya_gpu"]
    if backend and backend not in valid_backends:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Backend: {backend}. Erlaubt: {', '.join(valid_backends)}"
        )

    # 3. Validate language parameter
    valid_languages = ["de", "en"]
    if language and language not in valid_languages:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Sprache: {language}. Erlaubt: {', '.join(valid_languages)}"
        )

    try:
        # Save all files with validation
        saved_paths = []
        total_size_mb = 0
        allowed_extensions = settings.ALLOWED_EXTENSIONS

        for file in files:
            # Validate each file
            file_ext = Path(file.filename).suffix.lower() if file.filename else ""
            if not file_ext or file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungültiger Dateityp '{file.filename}'. Erlaubt: {', '.join(allowed_extensions)}"
                )

            file_content = await file.read()
            file_size_mb = len(file_content) / (1024 * 1024)
            total_size_mb += file_size_mb

            if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
                raise HTTPException(
                    status_code=413,
                    detail=f"Datei '{file.filename}' zu groß: {file_size_mb:.1f}MB. Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB"
                )

            saved_path = await ocr_service.save_upload(file_content, file.filename)
            saved_paths.append(saved_path)

        logger.info(
            "batch_validation_passed",
            file_count=len(files),
            total_size_mb=round(total_size_mb, 2),
            backend=backend
        )

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
async def test_german_text(
    text: str = Form(..., max_length=50000, description="Zu validierender Text (max 50KB)")
):
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