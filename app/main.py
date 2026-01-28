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
from app.middleware import RateLimitMiddleware, DevelopmentRateLimitBypass, SecurityHeadersMiddleware, RequestSizeLimitMiddleware, CSRFMiddleware, get_csrf_token_response, IPBlockingMiddleware, CompanyContextMiddleware
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
from app.api.v1.websocket import startup_realtime_services, shutdown_realtime_services
from app.core.backpressure import (
    backpressure_dependency,
    get_backpressure_info,
    add_backpressure_headers,
    BackpressureStatus,
)
from app.api.dependencies import get_current_active_user, get_current_superuser, get_db
from app.db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security.safe_module_loader import lock_bpmn_registration

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

    # Initialize Realtime WebSocket Services
    try:
        await startup_realtime_services()
        logger.info("realtime_services_started")
    except Exception as e:
        logger.warning("realtime_services_startup_failed", error=str(e))

    # SECURITY (CWE-470): Lock BPMN module registration after startup
    # Prevents runtime whitelist modification attacks
    try:
        lock_bpmn_registration()
        logger.info("bpmn_registration_locked", message="BPMN-Modul-Registrierung gesperrt")
    except Exception as e:
        logger.error("bpmn_registration_lock_failed", error=str(e))
        raise RuntimeError(
            "SICHERHEITSFEHLER: BPMN-Registrierungssperre konnte nicht aktiviert werden!"
        )

    logger.info("api_started")

    yield

    # Shutdown
    logger.info("api_shutting_down")

    # Shutdown Realtime WebSocket Services
    try:
        await shutdown_realtime_services()
        logger.info("realtime_services_stopped")
    except Exception as e:
        logger.warning("realtime_services_shutdown_failed", error=str(e))

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
    {
        "name": "Firmen",
        "description": "Multi-Mandanten Firmenverwaltung. Firmenwechsel, Benutzer-Zuordnungen und Berechtigungen.",
    },
    {
        "name": "Kassenbuch - Kassen",
        "description": "Kassenverwaltung. Kassen erstellen, bearbeiten und Salden verwalten.",
    },
    {
        "name": "Kassenbuch - Eintraege",
        "description": "GoBD-konforme Kassenbucheintraege. APPEND-ONLY, Stornierung nur durch Gegenbuchung.",
    },
    {
        "name": "Kassenbuch - Kassensturz",
        "description": "Kassensturz-Protokolle. Zaehlung mit automatischer Differenz-Buchung.",
    },
    {
        "name": "Kassenbuch - Berichte",
        "description": "Kassenbuch-Berichte. Zusammenfassungen und Tagesabschluesse.",
    },
    {
        "name": "Kassenbuch - Kategorien",
        "description": "Kassenbuch-Kategorien mit SKR03/SKR04 Kontenzuordnung.",
    },
    {
        "name": "comments",
        "description": "Dokumenten-Kommentare. Kommentieren, Antworten, @Mentions und Reaktionen fuer Enterprise-Collaboration.",
    },
    {
        "name": "notifications",
        "description": "Benutzer-Benachrichtigungen. Mentions, Replies, Sharing-Benachrichtigungen mit Gelesen-Status.",
    },
    {
        "name": "activity",
        "description": "Dokumenten-Aktivitaetsverlauf. Audit-Trail aller Aktionen auf Dokumenten.",
    },
    {
        "name": "Spesen - Abrechnungen",
        "description": "Spesenabrechnungen. CRUD und Positionsverwaltung.",
    },
    {
        "name": "Spesen - Positionen",
        "description": "Spesenpositionen. Belege, Kilometergeld, Verpflegungspauschalen.",
    },
    {
        "name": "Spesen - Workflow",
        "description": "Spesenabrechnung-Workflow. Einreichen, Genehmigen, Ablehnen, Auszahlen.",
    },
    {
        "name": "Spesen - Rechner",
        "description": "Berechnungen fuer Kilometergeld und Verpflegungspauschalen.",
    },
    {
        "name": "Contracts",
        "description": "Vertragsmanagement. Vertragslaufzeiten, Kuendigungsfristen, Verlaengerungsoptionen, Meilensteine und Nachtraege.",
    },
    {
        "name": "Dokumentvorlagen",
        "description": "Dokumentvorlagen-System. Templates mit Jinja2-Syntax, Variablen-Platzhalter, Ein-Klick Dokumentenerstellung, Textbausteine.",
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
# J.5 SECURITY FIX: In Production NUR explizite Origins, in Development zusaetzlich localhost
_cors_origins = settings.CORS_ORIGINS.copy()
if settings.DEBUG:
    # Nur in Development (DEBUG=True): localhost Origins hinzufuegen
    _cors_origins.extend(settings.CORS_DEVELOPMENT_ORIGINS)
elif not _cors_origins:
    # In Production OHNE konfigurierte Origins: Warnung ausgeben
    logger.warning(
        "cors_no_origins_configured",
        message="CORS_ORIGINS ist leer in Production - keine Cross-Origin-Requests erlaubt!"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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

# Add Company Context middleware
# Setzt die aktuelle Firma aus X-Company-ID Header oder User-Session
app.add_middleware(CompanyContextMiddleware)

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
from app.api.v1.trash import router as trash_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.search import router as search_router
from app.api.v1.unified_search import router as unified_search_router
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
from app.api.v1.banking import router as banking_router
from app.api.v1.banking_fints import fints_router, sepa_router, dashboard_router as banking_dashboard_router
from app.api.v1.datev import router as datev_router
from app.api.v1.finance import router as finance_router
from app.api.v1.exports import router as exports_router
from app.api.v1.scheduled_exports import router as scheduled_exports_router
from app.api.v1.companies import router as companies_router
from app.api.v1.cash import router as cash_router
from app.api.v1.expenses import router as expenses_router
from app.api.v1.streckengeschaeft import router as streckengeschaeft_router
from app.api.v1.privat import router as privat_router
from app.api.v1.privat_analytics import router as privat_analytics_router
from app.api.v1.personal import router as personal_router
from app.api.v1.validation import router as validation_router
from app.api.v1.comments import router as comments_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.document_tasks import router as document_tasks_router
from app.api.v1.activity import router as activity_router
from app.api.v1.archive import router as archive_router
from app.api.v1.tax_advisor import router as tax_advisor_router
from app.api.v1.dashboards import router as dashboards_router  # Enterprise Dashboard API
from app.api.v1.imports import router as imports_router
from app.api.v1.ai_autonomy import router as ai_autonomy_router
from app.api.v1.reports import router as reports_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.push_notifications import router as push_notifications_router
from app.api.v1.notification_rules import router as notification_rules_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.ai import router as ai_router
from app.api.v1.lexware import router as lexware_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.oneclick import router as oneclick_router
from app.api.v1.document_chains import router as document_chains_router
from app.api.v1.hygiene import router as hygiene_router
from app.api.v1.tax_advisor_packages import router as tax_advisor_packages_router
from app.api.v1.accounting import router as accounting_router
from app.api.v1.calendar import router as calendar_router
from app.api.v1.magic_buttons import router as magic_buttons_router
from app.api.v1.contracts import router as contracts_router
from app.api.v1.document_templates import router as document_templates_router
from app.api.v1.supplier_ranking import router as supplier_ranking_router
from app.api.v1.payment_behavior import router as payment_behavior_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.slack import router as slack_router
from app.api.v1.shipments import router as shipments_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.predictive_actions import router as predictive_actions_router
from app.api.v1.smart_escalation import router as smart_escalation_router
from app.api.v1.tenant_rate_limits import router as tenant_rate_limits_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.holding import router as holding_router
from app.api.v1.predictive_cashflow import router as predictive_cashflow_router
from app.api.v1.fraud_detection import router as fraud_detection_router
from app.api.v1.risk_intelligence import router as risk_intelligence_router
from app.api.v1.ocr_learning import router as ocr_learning_router
from app.api.v1.bpmn import router as bpmn_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.dpia import router as dpia_router
from app.api.v1.help import router as help_router
from app.api.v1.mfa import router as mfa_router
from app.api.v1.dlp import router as dlp_router
from app.api.v1.transactions import router as transactions_router
from app.api.v1.teams import router as teams_router
from app.api.v1.delegations import router as delegations_router
from app.api.v1.activity_timeline import router as activity_timeline_router
from app.api.v1.rules import router as rules_router
from app.api.v1.proactive_insights import router as proactive_insights_router
from app.api.v1.compare import router as compare_router
from app.api.v1.routing import router as routing_router
from app.api.v1.hardware import router as hardware_router
from app.api.v1.saved_filters import router as saved_filters_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.finance_assistant import router as finance_assistant_router
from app.api.v1.ai_conversations import router as ai_conversations_router
from app.api.v1.zero_touch import router as zero_touch_router
from app.api.v1.nlq import router as nlq_router
from app.api.v1.smart_inbox import router as smart_inbox_router
from app.api.v1.ceo_dashboard import router as ceo_dashboard_router
from app.api.v1.knowledge_graph import router as knowledge_graph_router
from app.api.v1.audit_chain import router as audit_chain_router
from app.api.v1.ai_ethics import router as ai_ethics_router
from app.api.v1.event_sourcing import router as event_sourcing_router
from app.api.v1.graphql_api import router as graphql_api_router
from app.api.v1.sync import router as sync_router
from app.api.v1.template_engine import router as template_engine_router
from app.api.v1.enrichment import router as enrichment_router
from app.api.v1.compliance_autopilot import router as compliance_autopilot_router
from app.api.v1.annotations import router as annotations_router
from app.api.v1.visual_diff import router as visual_diff_router
from app.api.v1.life_events import router as life_events_router

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
app.include_router(trash_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(favorites_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(unified_search_router, prefix="/api/v1")
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
app.include_router(banking_router, prefix="/api/v1")
app.include_router(fints_router, prefix="/api/v1")
app.include_router(sepa_router, prefix="/api/v1")
app.include_router(banking_dashboard_router, prefix="/api/v1")
app.include_router(datev_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")
app.include_router(exports_router, prefix="/api/v1")
app.include_router(scheduled_exports_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(cash_router, prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")
app.include_router(streckengeschaeft_router, prefix="/api/v1")
app.include_router(privat_router, prefix="/api/v1")
app.include_router(privat_analytics_router, prefix="/api/v1")
app.include_router(personal_router, prefix="/api/v1")
app.include_router(validation_router, prefix="/api/v1")
app.include_router(comments_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(document_tasks_router, prefix="/api/v1")
app.include_router(activity_router, prefix="/api/v1")
app.include_router(archive_router, prefix="/api/v1")
app.include_router(tax_advisor_router, prefix="/api/v1")
app.include_router(dashboards_router, prefix="/api/v1")
app.include_router(imports_router, prefix="/api/v1")
app.include_router(ai_autonomy_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(push_notifications_router, prefix="/api/v1")
app.include_router(notification_rules_router, prefix="/api/v1")
app.include_router(orchestration_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(lexware_router, prefix="/api/v1")
app.include_router(invoices_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(oneclick_router, prefix="/api/v1")
app.include_router(document_chains_router, prefix="/api/v1")
app.include_router(hygiene_router, prefix="/api/v1")
app.include_router(tax_advisor_packages_router, prefix="/api/v1")
app.include_router(accounting_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(magic_buttons_router, prefix="/api/v1")
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(document_templates_router, prefix="/api/v1")
app.include_router(supplier_ranking_router, prefix="/api/v1")
app.include_router(payment_behavior_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(slack_router, prefix="/api/v1")
app.include_router(shipments_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/api/v1", tags=["websocket"])
app.include_router(predictive_actions_router, prefix="/api/v1")
app.include_router(smart_escalation_router, prefix="/api/v1")
app.include_router(tenant_rate_limits_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(holding_router, prefix="/api/v1")
app.include_router(predictive_cashflow_router, prefix="/api/v1")
app.include_router(fraud_detection_router, prefix="/api/v1")
app.include_router(risk_intelligence_router, prefix="/api/v1")
app.include_router(ocr_learning_router, prefix="/api/v1")
app.include_router(bpmn_router, prefix="/api/v1")
app.include_router(compliance_router, prefix="/api/v1")
app.include_router(dpia_router, prefix="/api/v1")
app.include_router(help_router, prefix="/api/v1")
app.include_router(mfa_router, prefix="/api/v1")
app.include_router(dlp_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")
app.include_router(delegations_router, prefix="/api/v1")
app.include_router(activity_timeline_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(proactive_insights_router, prefix="/api/v1")
app.include_router(compare_router, prefix="/api/v1")
app.include_router(routing_router, prefix="/api/v1")
app.include_router(hardware_router, prefix="/api/v1")
app.include_router(saved_filters_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(finance_assistant_router, prefix="/api/v1")  # Vision 2.0: KI-Finanzassistent
app.include_router(ai_conversations_router, prefix="/api/v1")  # Vision 2.0: KI-Konversationen Persistenz
app.include_router(zero_touch_router, prefix="/api/v1")  # Vision 2.0: Zero-Touch OCR
app.include_router(nlq_router, prefix="/api/v1")  # Vision 2.0: NLQ 2.0
app.include_router(smart_inbox_router, prefix="/api/v1")  # Vision 2.0: Smart Inbox
app.include_router(ceo_dashboard_router, prefix="/api/v1")  # Vision 2.0: CEO Dashboard
app.include_router(knowledge_graph_router, prefix="/api/v1")  # Vision 2.0: Knowledge Graph
app.include_router(audit_chain_router, prefix="/api/v1")  # Vision 2.0: Merkle Audit Trail
app.include_router(ai_ethics_router, prefix="/api/v1")  # Vision 2.0: KI-Ethik-Layer
app.include_router(event_sourcing_router, prefix="/api/v1")  # Vision 2.0: Event Sourcing
app.include_router(graphql_api_router, prefix="/api/v1")  # Vision 2.0: GraphQL
app.include_router(sync_router, prefix="/api/v1")  # Vision 2.0: Offline Sync
app.include_router(template_engine_router, prefix="/api/v1")  # Vision 2.0: Template Engine
app.include_router(enrichment_router, prefix="/api/v1")  # Vision 2.0: External Enrichment
app.include_router(compliance_autopilot_router, prefix="/api/v1")  # Vision 2.0: Compliance Autopilot
app.include_router(annotations_router, prefix="/api/v1")  # Vision 2.0: Annotations
app.include_router(visual_diff_router, prefix="/api/v1")  # Vision 2.0: Visual Diff
app.include_router(life_events_router, prefix="/api/v1")  # Vision 2.0: Life Events


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
async def get_gpu_status(
    current_user: User = Depends(get_current_active_user)  # CC.4 SECURITY FIX: Auth required
):
    """Get detailed GPU status. Requires authentication."""
    if not gpu_manager:
        raise HTTPException(status_code=503, detail=HTTPErrors.GPU_MANAGER_NOT_INITIALIZED)

    return gpu_manager.get_detailed_status()


# ==================== OCR Processing Endpoints ====================

@app.get("/ocr/backends")
async def get_ocr_backends(
    current_user: User = Depends(get_current_active_user)  # CC.5 SECURITY FIX: Auth required
):
    """Get available OCR backends and their status. Requires authentication."""
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
    run_quick_classification: Optional[bool] = Form(True),  # NEU: Quick Classification aktivieren
    cached_response: Optional[Dict[str, Any]] = Depends(check_idempotency),
    backpressure: Dict[str, Any] = Depends(backpressure_dependency),
    current_user: User = Depends(get_current_active_user),  # CC.1 SECURITY FIX: Auth required
    db: AsyncSession = Depends(get_db),  # NEU: DB Session fuer Quick Classification
):
    """
    Process a document with OCR and optional Quick Classification.

    NEU: Enterprise Upload Workflow mit Quick Classification + Temp Storage.
    Nach erfolgreichem OCR wird automatisch Quick Classification ausgefuehrt:
    - Dokumenttyp erkennen (Eingangs-/Ausgangsrechnung)
    - Entity-Matching (Lieferant/Kunde)
    - Rename-Vorschlag generieren
    - Datei temporaer speichern fuer Review-Modal

    Args:
        file: Document file (PDF, PNG, JPG, etc.)
        backend: OCR backend to use (auto, surya, got_ocr, deepseek)
        language: Target language (de, en)
        detect_layout: Whether to detect document layout
        run_quick_classification: Quick Classification + Temp Storage aktivieren (default: True)
        cached_response: Gecachte Antwort bei Idempotency-Key (automatisch geprüft)
        backpressure: Queue-Backpressure-Status (automatisch geprüft)

    Returns:
        OCR processing result with:
        - text: Extrahierter Text
        - quick_classification: Direction, Entity-Match, Tags (wenn aktiviert)
        - rename_suggestion: Vorgeschlagener Dateiname (wenn aktiviert)
        - temp_file_id: ID fuer temporaere Datei (wenn aktiviert)

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
        # Only cache results with sufficient quality (confidence > 10% and text extracted)
        # This prevents caching of failed/empty OCR results
        ocr_confidence = result.get("confidence", 0.0)
        ocr_text = result.get("text", "")
        should_cache = (
            result.get("success")
            and ocr_confidence >= 0.1  # Minimum 10% confidence
            and len(ocr_text.strip()) > 10  # Minimum 10 characters
        )
        if should_cache:
            await cache_ocr_result(
                content=file_content,
                backend=actual_backend,
                result=result,
                language=language or "de"
            )
        elif result.get("success") and not should_cache:
            logger.info(
                "ocr_result_not_cached_low_quality",
                confidence=ocr_confidence,
                text_length=len(ocr_text),
                backend=actual_backend,
                filename=file.filename
            )

        # ========================================================================
        # NEU: Enterprise Upload Workflow - Quick Classification + Temp Storage
        # ========================================================================
        # DEBUG: Log condition values
        logger.info(
            "quick_classification_condition_check",
            run_quick_classification=run_quick_classification,
            run_quick_classification_type=type(run_quick_classification).__name__,
            result_success=result.get("success"),
            result_text_length=len(result.get("text", "") or ""),
            result_keys=list(result.keys()) if result else [],
        )
        if run_quick_classification and result.get("success") and result.get("text"):
            try:
                import uuid as uuid_module
                from app.services.quick_classification_service import QuickClassificationService
                from app.services.temp_file_storage import get_temp_file_storage

                ocr_text = result.get("text", "")
                temp_doc_id = uuid_module.uuid4()  # Temporaere ID fuer Classification

                # 1. Quick Classification ausfuehren
                logger.info("quick_classification_starting", filename=file.filename)
                quick_service = QuickClassificationService()
                classification_result = await quick_service.classify_document(
                    document_id=temp_doc_id,
                    ocr_text=ocr_text,
                    db=db,
                    auto_assign_tag=False  # Kein Tag zuweisen - nur klassifizieren
                )

                # 2. Ergebnis in Response einbauen
                result["quick_classification"] = {
                    "direction": classification_result.direction.value if classification_result.direction else None,
                    "confidence": classification_result.confidence,
                    "reason": classification_result.reason,
                    "extracted_vat_ids": classification_result.extracted_vat_ids,
                    "extracted_ibans": classification_result.extracted_ibans,
                    "matched_entity_id": str(classification_result.matched_entity_id) if classification_result.matched_entity_id else None,
                    "matched_entity_name": classification_result.matched_entity_name,
                    "matched_entity_type": classification_result.matched_entity_type,
                    "entity_match_method": classification_result.entity_match_method,
                    "entity_confidence": classification_result.entity_confidence,
                }

                # 2b. Structured Extraction fuer Datum, Betrag, Belegnummer
                # Nutzt StructuredExtractionService fuer vollstaendige Datenextraktion
                extracted_data = None
                if ocr_text and len(ocr_text) > 50:
                    try:
                        from app.services.structured_extraction_service import (
                            StructuredExtractionService,
                            get_structured_extraction_service,
                        )
                        extraction_service = get_structured_extraction_service()
                        extraction_result = await extraction_service.extract(
                            text=ocr_text,
                            document_id=None,  # Temp file, kein Document noch
                            tables=None,
                            detected_language=language,
                            db=db,
                        )
                        if extraction_result:
                            # Invoice-Daten extrahieren falls vorhanden
                            invoice = extraction_result.invoice
                            if invoice:
                                extracted_data = {
                                    "document_number": invoice.invoice_number,
                                    "document_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                                    "total_amount": float(invoice.gross_amount) if invoice.gross_amount else None,
                                    "currency": invoice.currency.value if hasattr(invoice.currency, 'value') else str(invoice.currency),
                                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                                    "vendor_name": invoice.sender.company if invoice.sender and invoice.sender.company else None,
                                    "extraction_confidence": extraction_result.overall_confidence,
                                }
                            else:
                                # Fallback: Allgemeine Daten aus classification
                                extracted_data = {
                                    "document_number": None,
                                    "document_date": None,
                                    "total_amount": float(extraction_result.amounts[0]) if extraction_result.amounts else None,
                                    "currency": "EUR",
                                    "due_date": None,
                                    "vendor_name": extraction_result.companies[0] if extraction_result.companies else None,
                                    "extraction_confidence": extraction_result.overall_confidence,
                                }
                        logger.info(
                            "structured_extraction_completed",
                            filename=file.filename,
                            has_invoice_data=extracted_data is not None and extracted_data.get("document_number") is not None,
                            extraction_confidence=extracted_data.get("extraction_confidence") if extracted_data else 0,
                        )
                    except Exception as se_error:
                        # Structured Extraction Fehler sollen OCR nicht abbrechen
                        logger.warning(
                            "structured_extraction_failed",
                            filename=file.filename,
                            error=str(se_error)
                        )
                        extracted_data = None

                # Extracted data zum quick_classification hinzufuegen
                result["quick_classification"]["extracted_data"] = extracted_data

                # 3. Rename-Vorschlag (bereits in classification_result enthalten)
                result["rename_suggestion"] = classification_result.rename_suggestion

                # 4. Datei temporaer speichern (fuer spaeteres Ablegen)
                temp_storage = get_temp_file_storage()

                # MIME-Type aus Dateiendung
                file_ext = Path(file.filename).suffix.lower() if file.filename else ""
                mime_map = {
                    ".pdf": "application/pdf",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".tiff": "image/tiff",
                    ".tif": "image/tiff",
                    ".bmp": "image/bmp",
                }
                detected_mime = mime_map.get(file_ext, "application/octet-stream")

                temp_file_info = await temp_storage.store(
                    file_content=file_content,
                    original_filename=file.filename or "unknown",
                    mime_type=detected_mime,
                    user_id=str(current_user.id),
                    metadata={
                        "ocr_backend": actual_backend,
                        "language": language,
                        "quick_classification": result["quick_classification"],
                    }
                )

                result["temp_file_id"] = temp_file_info.temp_file_id
                result["temp_file_expires_in_seconds"] = 3600  # 1 Stunde

                logger.info(
                    "quick_classification_completed",
                    filename=file.filename,
                    direction=classification_result.direction.value if classification_result.direction else None,
                    confidence=classification_result.confidence,
                    matched_entity=classification_result.matched_entity_name,
                    rename_suggestion=classification_result.rename_suggestion.get("suggested_filename") if classification_result.rename_suggestion else None,
                    temp_file_id=temp_file_info.temp_file_id
                )

            except Exception as qc_error:
                # Quick Classification Fehler sollen OCR nicht abbrechen
                logger.warning(
                    "quick_classification_failed",
                    filename=file.filename,
                    error=str(qc_error)
                )
                result["quick_classification"] = None
                result["quick_classification_error"] = str(qc_error)
                result["rename_suggestion"] = None
                result["temp_file_id"] = None

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
    backpressure: Dict[str, Any] = Depends(backpressure_dependency),
    current_user: User = Depends(get_current_active_user)  # CC.2 SECURITY FIX: Auth required
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
    text: str = Form(..., max_length=50000, description="Zu validierender Text (max 50KB)"),
    current_user: User = Depends(get_current_active_user)  # CC.3 SECURITY FIX: Auth required
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
async def get_statistics(
    current_user: User = Depends(get_current_active_user)  # CC.6 SECURITY FIX: Auth required
):
    """Get OCR processing statistics. Requires authentication."""
    if not ocr_service:
        raise HTTPException(status_code=503, detail=HTTPErrors.OCR_SERVICE_NOT_INITIALIZED)

    return await ocr_service.get_stats()


# ==================== System Monitoring Endpoint ====================

@app.get("/monitoring/system")
async def get_system_status(
    current_user: User = Depends(get_current_superuser)  # CC.7 SECURITY FIX: Admin required
):
    """
    Get comprehensive system status including CPU, RAM, GPU, and OCR metrics.
    Requires admin authentication.

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
async def get_monitoring_health(
    current_user: User = Depends(get_current_superuser)  # CC.8 SECURITY FIX: Admin required
):
    """
    Get system health status for monitoring and alerting.
    Requires admin authentication.

    Returns:
        Health status of all system components
    """
    monitor = get_system_monitor()
    return monitor.check_health()


# ==================== Rate Limit Status Endpoint ====================

@app.get("/ratelimit/status")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_superuser)  # CC.9 SECURITY FIX: Admin required
):
    """
    Get rate limiting status and statistics.
    Requires admin authentication.

    Returns:
        Rate limit configuration and statistics
    """
    from app.middleware import get_rate_limit_stats

    return get_rate_limit_stats()


@app.get("/ratelimit/info")
async def get_rate_limit_info_endpoint(
    request: Request,
    current_user: User = Depends(get_current_active_user)  # CC.10 SECURITY FIX: Auth required
):
    """
    Get rate limit information for current request.
    Requires authentication.

    Returns:
        Current user's rate limit information
    """
    from app.core.rate_limiting import get_rate_limit_info

    return get_rate_limit_info(request)


# ==================== Backpressure Status Endpoint ====================

@app.get("/backpressure/status")
async def get_backpressure_status_endpoint(
    current_user: User = Depends(get_current_active_user)  # EE.1 SECURITY FIX: Auth required
):
    """
    Get current backpressure status for queue monitoring.

    **REQUIRES AUTHENTICATION**

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
