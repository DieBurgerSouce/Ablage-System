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
from app.gpu_manager import GPUManager, get_memory_guard
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
from app.middleware.profiling import ProfilingMiddleware
from app.core.config import settings
from app.core.monitoring import get_system_monitor, PerformanceTimer
from app.core.german_messages import HTTPErrors, StatusMessages
from app.services.storage_service import cleanup_storage_service
from app.services.webhook_dispatcher import get_webhook_dispatcher
from app.core.idempotency import check_idempotency, get_idempotency_service
from app.services.ocr_cache_service import get_ocr_cache_service, get_cached_ocr_result, cache_ocr_result
from app.core.exception_handlers import register_exception_handlers
from app.services.model_preloader import get_model_preloader, preload_ocr_models
from app.core.backpressure import (
    backpressure_dependency,
    get_backpressure_info,
    add_backpressure_headers,
    BackpressureStatus,
)

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
memory_guard = None  # P0: GPU Memory Guard mit proaktivem Monitor
model_preloader = None  # P1: Model Pre-Loading fuer schnellere erste Anfragen

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
    global gpu_manager, german_validator, ocr_service, redis_storage, memory_guard, model_preloader

    # Startup
    logger.info("api_starting")

    # SECURITY: Production Debug Check
    # Verhindert versehentlich aktivierten Debug-Modus in Production
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        if settings.DEBUG:
            logger.critical(
                "production_debug_mode_detected",
                message="DEBUG=True in Production-Umgebung erkannt! "
                        "Dies ist ein Sicherheitsrisiko. Setze DEBUG=False."
            )
            raise RuntimeError(
                "SICHERHEITSFEHLER: DEBUG=True ist in Production nicht erlaubt! "
                "Setze DEBUG=False oder entferne ENVIRONMENT=production."
            )

    # Initialize managers
    gpu_manager = GPUManager()
    german_validator = GermanValidator()
    ocr_service = OCRService()

    # Initialize OpenTelemetry Tracing
    try:
        from app.core.telemetry import init_telemetry, set_system_info
        otlp_endpoint = getattr(settings, "OTLP_ENDPOINT", None) or os.getenv("OTLP_ENDPOINT")
        init_telemetry(
            service_name="ablage-system-ocr",
            otlp_endpoint=otlp_endpoint
        )
        set_system_info(
            version=getattr(settings, "APP_VERSION", "1.0.0"),
            environment=os.getenv("ENVIRONMENT", "development")
        )
        logger.info(
            "telemetry_initialized",
            otlp_enabled=otlp_endpoint is not None
        )
    except Exception as e:
        logger.warning("telemetry_init_failed", error=str(e))

    # Initialize Database Query Metrics
    try:
        from app.api.dependencies import engine
        from app.middleware.db_metrics import setup_db_metrics
        setup_db_metrics(engine)
        logger.info("db_query_metrics_initialized")
    except Exception as e:
        logger.warning("db_query_metrics_init_failed", error=str(e))

    # P0: Initialize GPU Memory Guard with proactive monitoring
    # Prevents 80% of OOM errors through proactive cache cleanup
    memory_guard = get_memory_guard()
    try:
        await memory_guard.start_memory_monitor()
        logger.info(
            "gpu_memory_monitor_initialized",
            interval=memory_guard.MONITOR_INTERVAL_SECONDS,
            proactive_threshold=memory_guard.PROACTIVE_CLEANUP_THRESHOLD
        )
    except Exception as e:
        logger.warning("gpu_memory_monitor_start_failed", error=str(e))

    # Initialize rate limiting Redis storage
    if settings.RATE_LIMIT_ENABLED:
        redis_storage = await get_redis_storage()
        # FIX P0.5: Store redis_storage in app.state for middleware late binding
        # The RateLimitMiddleware is created before lifespan runs, so it can't
        # receive redis_storage at construction time. This enables the middleware
        # to access redis_storage via app.state.redis_storage property fallback.
        app.state.redis_storage = redis_storage
        logger.info("rate_limiting_enabled", redis_available=redis_storage.is_available if redis_storage else False)

    logger.info("available_ocr_backends", backends=ocr_service.backend_manager.get_available_backends())

    # P1: Model Pre-Loading - Laedt OCR-Modelle im Background vor
    # Reduziert Cold-Start-Latenz fuer erste Anfragen um 10-30 Sekunden
    model_preloader = get_model_preloader()
    preload_enabled = getattr(settings, "MODEL_PRELOAD_ENABLED", True)

    if preload_enabled:
        include_gpu = gpu_manager.has_gpu() if gpu_manager else False
        logger.info(
            "model_preload_starting",
            include_gpu=include_gpu,
            background=True
        )
        try:
            # Background-Loading: Blockiert nicht den Startup
            await preload_ocr_models(
                include_gpu=include_gpu,
                background=True
            )
        except Exception as e:
            logger.warning("model_preload_startup_error", error=str(e))
    else:
        logger.info("model_preload_disabled_by_config")

    logger.info("api_started")

    yield

    # Shutdown
    logger.info("api_shutting_down")

    # P1: Cleanup Model Preloader
    if model_preloader:
        try:
            await model_preloader.cleanup()
            logger.info("model_preloader_cleanup_complete")
        except Exception as e:
            logger.warning("model_preloader_cleanup_failed", error=str(e))

    # P0: Stop GPU Memory Monitor
    if memory_guard:
        try:
            await memory_guard.stop_memory_monitor()
            logger.info("gpu_memory_monitor_stopped")
        except Exception as e:
            logger.warning("gpu_memory_monitor_stop_failed", error=str(e))

    if ocr_service:
        await ocr_service.cleanup()
    if redis_storage:
        await redis_storage.disconnect()
    # Cleanup webhook dispatcher HTTP client
    try:
        webhook_dispatcher = get_webhook_dispatcher()
        await webhook_dispatcher.close()
        logger.info("webhook_dispatcher_cleanup_complete")
    except Exception as e:
        logger.warning("webhook_dispatcher_cleanup_failed", error=str(e))
    # Cleanup storage service (MinIO client)
    await cleanup_storage_service()
    logger.info("api_shutdown_complete")


# OpenAPI Configuration
OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "Authentifizierung und Benutzerverwaltung. JWT-Token-basierte Authentifizierung mit 2FA-Unterstuetzung.",
    },
    {
        "name": "documents",
        "description": "Dokumentenverwaltung und -verarbeitung. Upload, Suche und Verwaltung von Dokumenten.",
    },
    {
        "name": "ocr",
        "description": "OCR-Verarbeitung mit mehreren Backends (DeepSeek, GOT-OCR, Surya). GPU-beschleunigte Textextraktion.",
    },
    {
        "name": "health",
        "description": "System-Health-Checks und Statusabfragen für Monitoring.",
    },
    {
        "name": "admin",
        "description": "Administratorfunktionen. Benutzerverwaltung, System-Dashboard und Audit-Logs.",
    },
    {
        "name": "backup",
        "description": "Backup- und Wiederherstellungsfunktionen. Automatische und manuelle Backups.",
    },
    {
        "name": "gdpr",
        "description": "DSGVO-Compliance-Funktionen. Datenexport, Löschung und Einwilligungsverwaltung.",
    },
    {
        "name": "vault",
        "description": "HashiCorp Vault Integration für sichere Secrets-Verwaltung.",
    },
    {
        "name": "webhooks",
        "description": "Webhook-Konfiguration für externe Integrationen und Event-Benachrichtigungen.",
    },
    {
        "name": "metrics",
        "description": "Prometheus-Metriken und Business-Analytics für Monitoring.",
    },
    {
        "name": "errors",
        "description": "Error-Tracking und -Statistiken. Überwachung von Fehlern nach Kategorie mit Alert-Management.",
    },
    {
        "name": "profiling",
        "description": "Performance-Profiling. Endpoint-Latenz, Hot Paths, Memory-Snapshots und Optimierungsempfehlungen.",
    },
    {
        "name": "search",
        "description": "Volltextsuche und semantische Suche in Dokumenten mit Elasticsearch-Backend.",
    },
    {
        "name": "api-keys",
        "description": "API-Schlüssel-Verwaltung für programmatischen Zugriff und Integrationen.",
    },
    {
        "name": "batch-jobs",
        "description": "Batch-Verarbeitung und Job-Queue-Management für große Dokumentenmengen.",
    },
    {
        "name": "sharing",
        "description": "Dokumentenfreigabe und Zugriffssteuerung für Collaboration.",
    },
    {
        "name": "settings",
        "description": "Benutzer- und Systemeinstellungen. Präferenzen und Konfiguration.",
    },
    {
        "name": "favorites",
        "description": "Favoriten-Verwaltung für schnellen Zugriff auf wichtige Dokumente.",
    },
    {
        "name": "security",
        "description": "Security Audit und Sicherheitsprüfungen. Konfigurationsanalyse und Empfehlungen.",
    },
    {
        "name": "readiness",
        "description": "Production Readiness Checks. Deployment-Vorbereitung und System-Validierung.",
    },
    {
        "name": "log-analytics",
        "description": "Log-Analyse und Monitoring. Trend-Erkennung, Anomalien und Dashboard-Metriken.",
    },
    {
        "name": "Strukturierte Daten",
        "description": "Strukturierte Dokumenten-Extraktion. Rechnungen, Bestellungen, Vertraege mit automatischer Feld-Extraktion und Suche.",
    },
    {
        "name": "rag",
        "description": "RAG Intelligence Layer. Semantische Suche, Document Chunking, Chat mit LLM-Unterstuetzung.",
    },
    {
        "name": "rag-search",
        "description": "RAG-basierte Suche. Semantic Search, Hybrid Search, Chunk-Retrieval.",
    },
    {
        "name": "rag-chunks",
        "description": "Document Chunking. Dokumente in semantische Chunks teilen mit Embedding-Generierung.",
    },
    {
        "name": "rag-chat",
        "description": "Chat mit RAG-Kontext. Sessions, LLM-Antworten mit Quellenangaben.",
    },
    {
        "name": "rag-jobs",
        "description": "RAG Batch-Jobs. Bulk-Chunking, Customer Card Sync, Report-Generierung.",
    },
    {
        "name": "rag-customers",
        "description": "Customer Cards. Pre-computed Kundenzusammenfassungen mit LLM-Generierung.",
    },
]

OPENAPI_DESCRIPTION = """
# Ablage-System OCR API

Enterprise-Lösung für deutsche Dokumentenverarbeitung mit GPU-beschleunigter OCR.

## Hauptfunktionen

| Feature | Beschreibung |
|---------|--------------|
| **Multi-Backend OCR** | DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling |
| **Deutsche Textoptimierung** | Spezialisiert auf deutsche Dokumente mit Fraktur-Unterstützung |
| **GPU-Beschleunigung** | NVIDIA RTX 4080 optimiert für Echtzeit-Verarbeitung |
| **DSGVO-Konform** | Vollständige Compliance mit deutschem Datenschutzrecht |
| **Performance-Monitoring** | Integriertes Profiling, Error-Tracking und Prometheus-Metriken |
| **Enterprise Security** | JWT-Auth, 2FA, API-Keys, Rate-Limiting, Audit-Logs |

## Authentifizierung

Die API unterstützt mehrere Authentifizierungsmethoden:

### JWT Bearer Token (Standard)
```
Authorization: Bearer <access_token>
```
Tokens werden über `/api/v1/auth/login` abgerufen.

### API-Schlüssel (für Integrationen)
```
X-API-Key: <api_key>
```
API-Schlüssel werden über `/api/v1/api-keys` verwaltet.

## Rate Limiting

| Endpoint-Typ | Limit |
|--------------|-------|
| Standard | 100 Anfragen/Minute |
| Upload | 50 Anfragen/Minute |
| Auth | 20 Anfragen/Minute |
| Admin | 30 Anfragen/Minute |

Bei Überschreitung wird HTTP 429 zurückgegeben mit `Retry-After` Header.

## Fehlerbehandlung

Alle Fehlerantworten folgen diesem Format:

```json
{
  "fehler": "Kurze Fehlerbezeichnung",
  "nachricht": "Detaillierte Beschreibung auf Deutsch",
  "status_code": 400,
  "fehler_code": "E001",
  "zeitstempel": "2025-01-01T12:00:00Z",
  "pfad": "/api/v1/resource",
  "request_id": "req-abc123"
}
```

## Monitoring

- **Health Checks**: `/api/v1/health/*`
- **Prometheus Metriken**: `/api/v1/metrics/prometheus`
- **Error-Statistiken**: `/api/v1/errors/stats`
- **Performance-Profiling**: `/api/v1/profiling/summary`

## Webhooks

Konfigurieren Sie Webhooks für Event-Benachrichtigungen:
- `document.uploaded` - Dokument hochgeladen
- `document.processed` - OCR abgeschlossen
- `document.failed` - Verarbeitung fehlgeschlagen

## Support

Bei Problemen erstellen Sie ein Issue im [GitHub Repository](https://github.com/ablage-system/ocr).
"""

# Initialize FastAPI app
app = FastAPI(
    title="Ablage-System OCR",
    description=OPENAPI_DESCRIPTION,
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "Ablage-System Support",
        "url": "https://github.com/ablage-system/ocr",
        "email": "support@ablage-system.dev",
    },
    license_info={
        "name": "Proprietär",
        "url": "https://ablage-system.local/license",
    },
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "docExpansion": "none",
        "filter": True,
        "showExtensions": True,
    },
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

# Add profiling middleware
# Erfasst Request-Timings für Performance-Analyse
app.add_middleware(
    ProfilingMiddleware,
    track_memory=settings.DEBUG,  # Memory-Tracking nur in Debug-Modus
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

# Register all unified exception handlers
register_exception_handlers(app)

# Add limiter state to app for SlowAPI decorators
app.state.limiter = limiter

# Include API routers
from app.api.v1 import auth, tasks, metrics, ml, versions, documents, health, ocr, agents
from app.api.v1.admin import router as admin_router
from app.api.v1.backup import router as backup_router
from app.api.v1.vault import router as vault_router
from app.api.v1.gdpr import router as gdpr_router, admin_router as gdpr_admin_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.search import router as search_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.batch_jobs import router as batch_jobs_router
from app.api.v1.sharing import router as sharing_router
from app.api.v1.settings import router as settings_router
from app.api.v1.errors import router as errors_router
from app.api.v1.profiling import router as profiling_router
from app.api.v1.security import router as security_router
from app.api.v1.readiness import router as readiness_router
from app.api.v1.log_analytics import router as log_analytics_router
from app.api.v1.entities import router as entities_router
from app.api.v1.groups import router as groups_router
from app.api.v1.training import router as training_router
from app.api.v1.tunes import router as tunes_router
from app.api.v1.extracted_data import router as extracted_data_router
from app.api.v1.rag import router as rag_router
from app.api.v1.einvoice import router as einvoice_router

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
app.include_router(sharing_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(errors_router, prefix="/api/v1")
app.include_router(profiling_router, prefix="/api/v1")
app.include_router(security_router, prefix="/api/v1")
app.include_router(readiness_router, prefix="/api/v1")
app.include_router(log_analytics_router, prefix="/api/v1")
app.include_router(entities_router, prefix="/api/v1")
app.include_router(groups_router, prefix="/api/v1")
app.include_router(training_router, prefix="/api/v1")
app.include_router(tunes_router, prefix="/api/v1/tunes", tags=["tunes"])
app.include_router(extracted_data_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/v1")
app.include_router(einvoice_router, prefix="/api/v1")


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
    preloader_status = model_preloader.get_status() if model_preloader else None

    # P2: Backpressure Status
    try:
        backpressure_status = get_backpressure_info()
    except Exception as e:
        logger.debug("backpressure_info_failed", error=str(e))
        backpressure_status = {"enabled": False, "error": str(e)}

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
            },
            "model_preloader": {
                "enabled": preloader_status.get("enabled", False) if preloader_status else False,
                "completed": preloader_status.get("preload_completed", False) if preloader_status else False,
                "models_loaded": preloader_status.get("summary", {}).get("loaded", 0) if preloader_status else 0,
            },
            "backpressure": {
                "enabled": backpressure_status.get("enabled", False),
                "status": backpressure_status.get("current_status", "unknown"),
                "queue_length": backpressure_status.get("total_queue_length", 0),
            }
        }
    }

    # Determine overall health
    if not ocr_backends:
        health["status"] = "degraded"
        health["message"] = "No OCR backends available"

    # Check backpressure status
    bp_status = backpressure_status.get("current_status", "normal")
    if bp_status == BackpressureStatus.OVERLOADED:
        health["status"] = "degraded"
        health["message"] = "System ueberlastet - hohe Queue-Auslastung"
    elif bp_status == BackpressureStatus.CRITICAL:
        if health["status"] == "healthy":
            health["status"] = "warning"
            health["message"] = "Kritische Queue-Auslastung - Graceful Degradation aktiv"

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
    cached_response: Optional[Dict[str, Any]] = Depends(check_idempotency),
    backpressure: Dict[str, Any] = Depends(backpressure_dependency)
):
    """
    Process a document with OCR

    Args:
        file: Document file (PDF, PNG, JPG, etc.)
        backend: OCR backend to use (auto, surya, got_ocr, deepseek)
        language: Target language (de, en)
        detect_layout: Whether to detect document layout
        cached_response: Gecachte Antwort bei Idempotency-Key (automatisch geprüft)
        backpressure: Queue-Backpressure-Status (automatisch geprüft)

    Returns:
        OCR processing result with extracted text

    Headers:
        Idempotency-Key: Optional. Bei Wiederholung wird gecachtes Ergebnis zurückgegeben.
        X-Priority: Optional. Prioritaet der Anfrage (high, normal, low)
        X-Backpressure-Status: Response Header mit aktuellem Queue-Status

    Raises:
        HTTPException 503: Wenn System ueberlastet (Backpressure)
    """
    # P2: Backpressure - Backend-Empfehlung bei hoher Last
    suggested_backend = backpressure.get("suggested_backend")
    if suggested_backend and backend == "auto":
        logger.info(
            "backpressure_backend_override",
            original_backend=backend,
            suggested_backend=suggested_backend,
            queue_length=backpressure.get("queue_length", 0)
        )
        backend = suggested_backend

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
    request: Request,
    files: List[UploadFile] = File(...),
    backend: Optional[str] = Form("auto"),
    language: Optional[str] = Form("de"),
    backpressure: Dict[str, Any] = Depends(backpressure_dependency)
):
    """
    Process multiple documents in batch

    Args:
        files: List of document files (max 32 Dateien)
        backend: OCR backend to use
        language: Target language
        backpressure: Queue-Backpressure-Status (automatisch geprüft)

    Returns:
        List of OCR results

    Headers:
        X-Priority: Optional. Prioritaet der Anfrage (high, normal, low)

    Raises:
        HTTPException 503: Wenn System ueberlastet (Backpressure)
    """
    # P2: Backpressure - Bei Batch strengere Limits
    bp_status = backpressure.get("status", "normal")
    if bp_status in [BackpressureStatus.CRITICAL, BackpressureStatus.OVERLOADED]:
        # Bei kritischer Last: Batch-Groesse reduzieren
        max_batch = 8 if bp_status == BackpressureStatus.CRITICAL else 4
        if len(files) > max_batch:
            raise HTTPException(
                status_code=503,
                detail=f"System unter hoher Last. Batch-Groesse temporaer auf {max_batch} Dateien limitiert. "
                       f"Aktuelle Anfrage: {len(files)} Dateien."
            )

    # P2: Backpressure - Backend-Empfehlung bei hoher Last
    suggested_backend = backpressure.get("suggested_backend")
    if suggested_backend and backend == "auto":
        logger.info(
            "backpressure_batch_backend_override",
            original_backend=backend,
            suggested_backend=suggested_backend,
            queue_length=backpressure.get("queue_length", 0)
        )
        backend = suggested_backend

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


# ==================== Backpressure Status Endpoint ====================

@app.get("/backpressure/status")
async def get_backpressure_status_endpoint():
    """
    Get current backpressure status for queue monitoring.

    Returns backpressure information including:
    - Current status (normal, warning, critical, overloaded)
    - Queue lengths per queue
    - Thresholds and recommendations

    Use this endpoint for:
    - Monitoring dashboards
    - Alerting systems
    - Client-side backoff decisions

    Returns:
        Backpressure status and queue information
    """
    try:
        info = get_backpressure_info()
        return {
            "success": True,
            "backpressure": info
        }
    except Exception as e:
        logger.error("backpressure_status_error", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "backpressure": {
                "enabled": False,
                "current_status": "unknown"
            }
        }


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
