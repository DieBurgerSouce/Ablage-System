"""
Application configuration using Pydantic Settings.

Supports:
- Environment variables (.env file)
- HashiCorp Vault integration for secure secrets management
- Runtime secret rotation

Structure:
- config.py: Main Settings class (this file)
- config/validation.py: Security helper functions
- config/vault_client.py: Vault integration
- config/__init__.py: Module exports

Feinpoliert und durchdacht - Sichere Konfigurationsverwaltung.
"""

from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import secrets
import os

from pydantic import Field, field_validator, SecretStr, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog

# Import from modular config package
from app.core.config.validation import (
    calculate_entropy_bits,
    validate_secret_entropy,
    WEAK_PASSWORDS,
    MINIO_DEFAULT_USERS,
    MINIO_DEFAULT_PASSWORDS,
)
from app.core.config.vault_client import VaultClient, VAULT_AVAILABLE
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# VaultClient is now imported from app.core.config.vault_client
# See: app/core/config/vault_client.py


class Settings(BaseSettings):
    """Application settings with environment variable and Vault support."""

    # Application
    APP_NAME: str = "Ablage-System OCR"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    # Q.2 SECURITY FIX: Explizite Environment-Erkennung
    ENVIRONMENT: str = Field(
        default="development",
        description="Umgebung: development, staging, production"
    )

    @property
    def is_production(self) -> bool:
        """Zentrale, fail-safe Produktions-Erkennung.

        Deckt production/prod sowie Varianten wie prod-eu/production-eu
        (startswith), damit Sicherheits-Guards bei nicht-kanonischen
        Umgebungs-Labels nicht still durchrutschen.
        """
        return self.ENVIRONMENT.lower().startswith("prod")
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent  # Project root
    
    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False
    
    # System User (für automatisierte Operationen wie Auto-Posting)
    SYSTEM_USER_ID: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description="System-User UUID für automatisierte Operationen (Auto-Posting)"
    )

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    
    # Security
    # WICHTIG: SECRET_KEY MUSS in Production via Umgebungsvariable gesetzt werden!
    # Beispiel: SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
    # SECURITY FIX: SecretStr verhindert Logging von Secrets
    # J.3 CRITICAL FIX: Kein leerer Default mehr - muss explizit gesetzt werden
    SECRET_KEY: SecretStr = Field(
        ...,  # Required - kein Default!
        min_length=32,  # Mindestens 32 Zeichen
        description="JWT Secret Key - MUSS gesetzt sein (min. 32 Zeichen)"
    )
    # ENCRYPTION_KEY für TOTP-Secrets und andere sensible Daten
    # Optional: Wenn nicht gesetzt, wird aus SECRET_KEY abgeleitet
    # Generieren: python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    # SECURITY FIX: SecretStr verhindert Logging von Secrets
    ENCRYPTION_KEY: Optional[SecretStr] = Field(
        default=None,
        description="AES-256 Encryption Key (Base64-encoded, 32 Bytes)"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS - Sicherheitskonfiguration
    # J.5 SECURITY FIX: Production-Origins müssen explizit gesetzt werden
    # In Development: localhost erlaubt, in Production: CORS_ORIGINS MUSS gesetzt sein
    # Beispiel: CORS_ORIGINS=["https://app.ablage-system.local","https://admin.ablage-system.local"]
    CORS_ORIGINS: List[str] = Field(
        default_factory=list,  # Leere Liste = keine Origins erlaubt ohne Konfiguration
        description="Erlaubte CORS Origins - MUSS in Production explizit gesetzt werden!"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Credentials erlauben - nur mit expliziten Origins!"
    )
    # J.5 SECURITY FIX: Development-Only Origins (werden nur in non-production verwendet)
    CORS_DEVELOPMENT_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:80", "http://localhost"],
        description="Zusätzliche Origins NUR für Development - werden in Production ignoriert!"
    )
    # Eingeschränkte Methods - nur was benötigt wird
    CORS_ALLOW_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        description="Erlaubte HTTP Methods"
    )
    # Eingeschränkte Headers
    CORS_ALLOW_HEADERS: List[str] = Field(
        default=[
            "Accept",
            "Accept-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        description="Erlaubte Request Headers"
    )
    # Expose Headers für Client
    CORS_EXPOSE_HEADERS: List[str] = Field(
        default=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        description="Response Headers die dem Client exponiert werden"
    )
    # Max Age für Preflight Caching
    CORS_MAX_AGE: int = Field(
        default=600,
        description="Max Age für CORS Preflight Caching in Sekunden"
    )
    
    # Database
    DB_USER: str = "ablage_admin"
    # SECURITY FIX: Kein Default-Passwort - muss in .env gesetzt werden
    DB_PASSWORD: SecretStr = Field(..., description="Database password - REQUIRED, set in .env")
    DB_HOST: str = "localhost"
    DB_PORT: int = 5433
    DB_NAME: str = "ablage_system"
    DATABASE_URL: Optional[str] = None

    # Database SSL/TLS Configuration
    DB_SSL_MODE: str = Field(
        default="require",
        description="PostgreSQL SSL-Modus: disable, allow, prefer, require, verify-ca, verify-full"
    )
    DB_SSL_CERT: Optional[str] = Field(
        default=None,
        description="Pfad zum Client-SSL-Zertifikat"
    )
    DB_SSL_KEY: Optional[str] = Field(
        default=None,
        description="Pfad zum Client-SSL-Schluessel"
    )
    DB_SSL_ROOT_CERT: Optional[str] = Field(
        default=None,
        description="Pfad zum CA-Root-Zertifikat"
    )

    # Database Connection Pool Settings
    # API Pool (optimiert - Query Performance durch Composite Indexes verbessert)
    DB_POOL_SIZE: int = Field(default=15, description="Database connection pool size for API")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Maximum overflow connections for API")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Connection recycle time in seconds (30 min)")
    # PERFORMANCE FIX: 10s statt 60s - schnelleres Fail-Fast bei Pool-Erschöpfung
    DB_POOL_TIMEOUT: int = Field(default=10, description="Pool connection timeout in seconds")
    DB_POOL_PRE_PING: bool = Field(default=True, description="Validate connections before use")

    # Worker Pool Settings (Celery Tasks)
    DB_WORKER_POOL_SIZE: int = Field(default=5, description="Database pool size for workers")
    DB_WORKER_MAX_OVERFLOW: int = Field(default=10, description="Max overflow for workers")
    DB_WORKER_POOL_RECYCLE: int = Field(default=3600, description="Worker connection recycle time")

    # Callback Pool Settings (Task Callbacks - kurzlebig)
    DB_CALLBACK_POOL_SIZE: int = Field(default=3, description="Database pool size for callbacks")
    DB_CALLBACK_MAX_OVERFLOW: int = Field(default=5, description="Max overflow for callbacks")
    DB_CALLBACK_POOL_RECYCLE: int = Field(default=1800, description="Callback connection recycle time")

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[SecretStr] = None
    REDIS_URL: Optional[str] = None

    # Redis Connection Pool Settings
    REDIS_POOL_MIN_SIZE: int = 5
    REDIS_POOL_MAX_SIZE: int = 20
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_SOCKET_KEEPALIVE: bool = True
    REDIS_HEALTH_CHECK_INTERVAL: int = 30

    # Redis Sentinel (HA) - Set REDIS_SENTINEL_HOSTS to enable
    # Format: "host1:port1,host2:port2,host3:port3"
    REDIS_SENTINEL_HOSTS: Optional[str] = Field(
        default=None,
        description="Komma-getrennte Sentinel-Hosts (z.B. 'sentinel1:26379,sentinel2:26379,sentinel3:26379')"
    )
    REDIS_SENTINEL_MASTER_NAME: str = Field(
        default="mymaster",
        description="Name des Redis-Master-Sets in Sentinel-Konfiguration"
    )

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False  # For testing
    CELERY_TASK_EAGER_PROPAGATES: bool = True

    # Web Push (VAPID)
    # Generate keys with: python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print(v.private_key_raw, v.public_key_raw)"
    VAPID_PRIVATE_KEY: str = Field(
        default="",
        description="VAPID private key for Web Push - generate with py_vapid"
    )
    VAPID_PUBLIC_KEY: str = Field(
        default="",
        description="VAPID public key for Web Push subscriptions"
    )
    VAPID_CONTACT_EMAIL: str = Field(
        default="admin@ablage-system.local",
        description="Contact email for VAPID claims"
    )

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    # SECURITY FIX: Keine Default-Credentials - müssen in .env gesetzt werden
    MINIO_ACCESS_KEY: str = Field(..., description="MinIO access key - REQUIRED, set in .env")
    MINIO_SECRET_KEY: SecretStr = Field(..., description="MinIO secret key - REQUIRED, set in .env")
    MINIO_SECURE: bool = False
    MINIO_BUCKET_DOCUMENTS: str = "documents"
    MINIO_BUCKET_PROCESSED: str = "processed"
    MINIO_BUCKET_THUMBNAILS: str = "thumbnails"
    
    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]
    UPLOAD_DIR: Path = Path("/app/uploads")
    OUTPUT_DIR: Path = Path("/app/outputs")

    # =============================================================================
    # ClamAV Malware Scanning (SECURITY)
    # =============================================================================
    MALWARE_SCAN_ENABLED: bool = Field(
        default=True,
        description="Malware-Scanning für Document Uploads aktivieren"
    )
    MALWARE_SCAN_FAIL_CLOSED: bool = Field(
        default=True,
        description="Bei Scanner-Fehler Upload blockieren (fail-closed, empfohlen für Production)"
    )
    CLAMAV_HOST: str = Field(
        default="clamav",
        description="ClamAV Daemon Host"
    )
    CLAMAV_PORT: int = Field(
        default=3310,
        description="ClamAV Daemon Port"
    )
    CLAMAV_TIMEOUT: int = Field(
        default=60,
        ge=10, le=300,
        description="ClamAV Scan-Timeout in Sekunden"
    )
    CLAMAV_MAX_SIZE_MB: int = Field(
        default=100,
        ge=1, le=500,
        description="Maximale Dateigröße für ClamAV-Scan in MB"
    )
    
    # OCR Settings
    DEFAULT_OCR_BACKEND: str = "auto"
    DEFAULT_LANGUAGE: str = "de"
    OCR_TIMEOUT_SECONDS: int = 300  # 5 minutes
    MAX_PAGES_PER_DOCUMENT: int = 100
    
    # GPU Settings
    CUDA_VISIBLE_DEVICES: str = "0"
    GPU_MEMORY_FRACTION: float = Field(default=0.85, ge=0.0, le=1.0, description="Max VRAM usage (0.0-1.0)")
    ENABLE_GPU: bool = True
    GPU_BATCH_SIZE: int = Field(default=32, ge=1, le=128, description="GPU batch size (1-128)")

    # GPU Lock Settings (Distributed locking via Redis)
    # Increased from 60s to 180s for long-running OCR tasks
    GPU_LOCK_TIMEOUT: int = Field(default=180, description="GPU lock auto-expire timeout in seconds")
    GPU_LOCK_ACQUIRE_TIMEOUT: int = Field(default=300, description="Max seconds to wait for GPU lock")
    GPU_LOCK_RETRY_INTERVAL: float = Field(default=0.1, description="Seconds between lock acquisition retries")

    # Model Pre-Loading Settings
    # Laedt OCR-Modelle beim Startup vor für schnellere erste Anfragen
    MODEL_PRELOAD_ENABLED: bool = True
    MODEL_PRELOAD_GPU_MODELS: bool = True  # Ob GPU-Modelle vorgeladen werden
    MODEL_PRELOAD_TIMEOUT_SECONDS: int = 600  # Timeout pro Model (10 Min)
    WAIT_FOR_MODEL_PRELOAD: bool = False  # Block startup until models are loaded
    WAIT_FOR_MODEL_PRELOAD_TIMEOUT: int = 120  # Timeout in seconds for blocking preload

    # Load Balancing Settings
    LOAD_BALANCING_ENABLED: bool = True
    QUEUE_LENGTH_THRESHOLD_HIGH: int = 100  # Switch to faster backend
    QUEUE_LENGTH_THRESHOLD_CRITICAL: int = 200  # Use CPU fallback
    QUEUE_CHECK_INTERVAL_SECONDS: int = 30  # How often to check queues
    LOAD_BALANCE_PREFER_GPU: bool = True  # Prefer GPU when queues similar

    # CSRF Protection
    CSRF_ENABLED: bool = True  # Enable CSRF protection (Double-Submit-Cookie)

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_DOCUMENTS_PER_HOUR: int = 10
    DEFAULT_USER_DAILY_QUOTA: int = 100

    # Rate Limit Whitelist (comma-separated IPs)
    RATE_LIMIT_WHITELIST: List[str] = []

    # Rate Limit Tiers (Daily >= Hourly validated in model_validator)
    RATE_LIMIT_FREE_HOURLY: int = Field(default=10, ge=1, description="Hourly requests for free tier")
    RATE_LIMIT_FREE_DAILY: int = Field(default=50, ge=1, description="Daily requests for free tier")
    RATE_LIMIT_PREMIUM_HOURLY: int = Field(default=100, ge=1, description="Hourly requests for premium tier")
    RATE_LIMIT_PREMIUM_DAILY: int = Field(default=1000, ge=1, description="Daily requests for premium tier")
    RATE_LIMIT_ADMIN_HOURLY: int = Field(default=10000, ge=1, description="Hourly requests for admin tier")

    # Rate Limit Windows (in seconds)
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW: int = 900  # 15 minutes
    RATE_LIMIT_REGISTER_ATTEMPTS: int = 3
    RATE_LIMIT_REGISTER_WINDOW: int = 3600  # 1 hour

    # Rate Limit Storage
    RATE_LIMIT_STORAGE_URL: Optional[str] = None

    # Rate Limit Fail-Closed Mode
    # SECURITY FIX: Default auf True geändert (fail-closed ist sicherer)
    # Bei Redis-Ausfall werden Requests abgelehnt statt durchgelassen
    # Bei DDoS-Angriffen könnte sonst Rate Limiting umgangen werden
    RATE_LIMIT_FAIL_CLOSED: bool = True  # SECURITY: fail-closed für besseren Schutz bei Redis-Ausfall
    RATE_LIMIT_FAIL_CLOSED_CRITICAL: bool = True  # SECURITY: Kritische Endpoints (Login, OCR) immer schützen

    # Session Management
    # Maximale Anzahl gleichzeitiger Sessions pro Benutzer
    MAX_SESSIONS_PER_USER: int = 10
    # Session-Ablaufzeit in Stunden (Standard: 7 Tage)
    SESSION_EXPIRY_HOURS: int = 168  # 7 * 24
    # Session-Limit-Modus: "soft" (alte Sessions automatisch widerrufen) oder "hard" (Login blockieren)
    SESSION_LIMIT_MODE: str = "soft"
    # Bei "hard"-Modus: Nachricht wenn Limit erreicht
    SESSION_LIMIT_HARD_MESSAGE: str = "Maximale Anzahl aktiver Sessions erreicht. Bitte beenden Sie eine andere Session."

    # German Language Settings
    GERMAN_VALIDATION_ENABLED: bool = True
    MINIMUM_GERMAN_VALIDATION_SCORE: float = 0.7
    DETECT_FRAKTUR: bool = True

    # Historical German Normalization
    HISTORICAL_NORMALIZATION_ENABLED: bool = True
    HISTORICAL_NORM_PRE_1996: bool = True  # daß -> dass, muß -> muss
    HISTORICAL_NORM_TH: bool = True  # Thür -> Tür, Muth -> Mut
    HISTORICAL_NORM_C: bool = True  # Circus -> Zirkus, Classe -> Klasse
    HISTORICAL_NORM_PH: bool = True  # Telephon -> Telefon
    HISTORICAL_NORM_FRAKTUR: bool = True  # ſ -> s, ꝛ -> r

    # German Compound Splitter (für verbesserte Suche)
    COMPOUND_SPLITTING_ENABLED: bool = True
    COMPOUND_MIN_PART_LENGTH: int = 3  # Mindestlänge für Wortteile

    # Quality Assurance Settings
    QA_REVIEW_THRESHOLD: float = 0.7  # Trigger human review below this score
    QA_CONFIDENCE_THRESHOLD_HIGH: float = 0.9
    QA_CONFIDENCE_THRESHOLD_MEDIUM: float = 0.75
    QA_CONFIDENCE_THRESHOLD_LOW: float = 0.6

    # Search and Embedding Settings
    EMBEDDING_SERVICE_URL: Optional[str] = None  # HuggingFace TEI Service URL
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 16  # Optimiert für RTX 4080 16GB VRAM
    EMBEDDING_MAX_LENGTH: int = 512  # Max tokens per text

    # Dynamisches Batching (GPU-Speicher-basiert)
    EMBEDDING_DYNAMIC_BATCH_ENABLED: bool = True  # Dynamische Batch-Größe
    EMBEDDING_MIN_BATCH_SIZE: int = 4  # Minimum bei Speicherknappheit
    EMBEDDING_MAX_BATCH_SIZE: int = 32  # Maximum bei ausreichend Speicher
    EMBEDDING_GPU_MEMORY_THRESHOLD: float = 0.75  # Max 75% GPU-Speicher nutzen
    SEARCH_DEFAULT_LIMIT: int = 20
    SEARCH_MAX_LIMIT: int = 100
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5
    HYBRID_FTS_WEIGHT: float = 0.3
    HYBRID_SEMANTIC_WEIGHT: float = 0.7

    # Field-Level Boosting für FTS (Filename-Treffer ranken höher)
    FTS_FIELD_BOOST_FILENAME: float = 2.0  # Treffer im Dateinamen
    FTS_FIELD_BOOST_ORIGINAL_FILENAME: float = 1.8  # Treffer im Original-Dateinamen
    FTS_FIELD_BOOST_EXTRACTED_TEXT: float = 1.0  # Treffer im extrahierten Text (Basis)

    # Adaptive RRF-Gewichte basierend auf Query-Länge
    ADAPTIVE_RRF_WEIGHTS_ENABLED: bool = True  # Dynamische Gewichtung aktivieren
    HYBRID_WEIGHTS_SHORT_FTS: float = 0.5  # FTS-Gewicht für 1-2 Woerter
    HYBRID_WEIGHTS_SHORT_SEMANTIC: float = 0.5  # Semantic-Gewicht für 1-2 Woerter
    HYBRID_WEIGHTS_MEDIUM_FTS: float = 0.3  # FTS-Gewicht für 3-5 Woerter (Standard)
    HYBRID_WEIGHTS_MEDIUM_SEMANTIC: float = 0.7  # Semantic-Gewicht für 3-5 Woerter
    HYBRID_WEIGHTS_LONG_FTS: float = 0.2  # FTS-Gewicht für 6+ Woerter
    HYBRID_WEIGHTS_LONG_SEMANTIC: float = 0.8  # Semantic-Gewicht für 6+ Woerter

    # Search Caching Settings
    SEARCH_CACHE_ENABLED: bool = True
    SEARCH_CACHE_TTL: int = 3600  # 1 hour for search results
    SEARCH_EMBEDDING_CACHE_TTL: int = 86400  # 24 hours for query embeddings
    SEARCH_SIMILAR_CACHE_TTL: int = 1800  # 30 minutes for similar documents

    # Embedding Auto-Generation Settings
    EMBEDDING_AUTO_GENERATE: bool = True  # Auto-generate after OCR
    EMBEDDING_TASK_DELAY_SECONDS: int = 5  # Delay before embedding task
    EMBEDDING_TASK_PRIORITY: int = 9  # Celery priority (0-9, 9=lowest)

    # RAG Auto-Chunking Settings (nach OCR/Embedding)
    AUTO_RAG_CHUNKING_ENABLED: bool = True  # Auto-chunk documents after OCR
    RAG_CHUNKING_DELAY_SECONDS: int = 10  # Delay before chunking task
    RAG_TASK_PRIORITY: int = 7  # Celery priority (0-9, 9=lowest)

    # =============================================================================
    # Qdrant Vector Database (Parallel zu pgvector für A/B Testing)
    # =============================================================================
    QDRANT_ENABLED: bool = Field(
        default=False,
        description="Qdrant als parallele Vector-DB aktivieren"
    )
    QDRANT_HOST: str = Field(default="localhost", description="Qdrant Host")
    QDRANT_HTTP_PORT: int = Field(default=6333, description="Qdrant REST API Port")
    QDRANT_GRPC_PORT: int = Field(default=6334, description="Qdrant gRPC Port")
    QDRANT_PREFER_GRPC: bool = Field(
        default=True,
        description="gRPC bevorzugen (schneller als REST)"
    )
    QDRANT_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Qdrant API Key (optional, für Cloud)"
    )
    # Collection Names
    QDRANT_COLLECTION_DOCUMENTS: str = Field(
        default="ablage_documents",
        description="Collection für Document-Embeddings"
    )
    QDRANT_COLLECTION_CHUNKS: str = Field(
        default="ablage_chunks",
        description="Collection für RAG-Chunk-Embeddings"
    )
    # HNSW Index Konfiguration
    QDRANT_HNSW_M: int = Field(
        default=16,
        ge=4, le=64,
        description="HNSW m Parameter (Kanten pro Knoten)"
    )
    QDRANT_HNSW_EF_CONSTRUCT: int = Field(
        default=128,
        ge=16, le=512,
        description="HNSW ef_construct (Index-Qualitaet)"
    )
    QDRANT_ON_DISK_PAYLOAD: bool = Field(
        default=True,
        description="Payloads auf Disk speichern (weniger RAM)"
    )
    # Quantization
    QDRANT_QUANTIZATION_ENABLED: bool = Field(
        default=False,
        description="Scalar Quantization aktivieren (weniger Speicher)"
    )

    # =============================================================================
    # Jina Embeddings (Spezialisiert für deutsche Dokumente)
    # =============================================================================
    JINA_EMBEDDING_ENABLED: bool = Field(
        default=False,
        description="Jina-Embeddings-v2-base-de als Alternative aktivieren"
    )
    JINA_EMBEDDING_MODEL: str = Field(
        default="jinaai/jina-embeddings-v2-base-de",
        description="Jina Embedding Modell (161M params, 8k Token-Kontext)"
    )
    JINA_EMBEDDING_DIMENSION: int = Field(
        default=1024,
        description="Jina Embedding Dimension"
    )
    JINA_EMBEDDING_MAX_LENGTH: int = Field(
        default=8192,
        description="Jina max Token-Kontext (8k vs 512 bei E5)"
    )
    JINA_TRUST_REMOTE_CODE: bool = Field(
        default=True,
        description="trust_remote_code für HuggingFace (required für Jina)"
    )

    # =============================================================================
    # Vector Search A/B Testing
    # =============================================================================
    VECTOR_AB_TESTING_ENABLED: bool = Field(
        default=False,
        description="A/B Testing zwischen pgvector und Qdrant aktivieren"
    )
    VECTOR_AB_TRAFFIC_SPLIT: int = Field(
        default=10,
        ge=0, le=100,
        description="Prozent Traffic zu Treatment (Qdrant) 0-100"
    )
    VECTOR_AB_CONTROL_BACKEND: str = Field(
        default="pgvector",
        description="Control Backend (pgvector oder qdrant)"
    )
    VECTOR_AB_TREATMENT_BACKEND: str = Field(
        default="qdrant",
        description="Treatment Backend (pgvector oder qdrant)"
    )
    VECTOR_AB_CONTROL_EMBEDDING: str = Field(
        default="intfloat/multilingual-e5-large",
        description="Embedding-Modell für Control"
    )
    VECTOR_AB_TREATMENT_EMBEDDING: str = Field(
        default="jinaai/jina-embeddings-v2-base-de",
        description="Embedding-Modell für Treatment"
    )
    VECTOR_AB_METRICS_ENABLED: bool = Field(
        default=True,
        description="Metriken für A/B Test sammeln"
    )

    # =============================================================================
    # Dual-Write Settings (Sync zwischen pgvector und Qdrant)
    # =============================================================================
    VECTOR_DUAL_WRITE_ENABLED: bool = Field(
        default=False,
        description="Embeddings in beide Backends schreiben"
    )
    VECTOR_DUAL_WRITE_ASYNC: bool = Field(
        default=True,
        description="Qdrant-Sync asynchron (Celery Task)"
    )
    VECTOR_MIGRATION_BATCH_SIZE: int = Field(
        default=1000,
        ge=100, le=10000,
        description="Batch-Größe für Embedding-Migration"
    )

    # Auto Ground-Truth Pipeline Settings
    # Bei 500+ Docs/Tag: High-Confidence OCR-Ergebnisse automatisch als Ground-Truth akzeptieren
    AUTO_GROUND_TRUTH_ENABLED: bool = True  # Enable auto ground-truth generation
    AUTO_GROUND_TRUTH_CONFIDENCE_THRESHOLD: float = 0.95  # Min confidence for auto-accept
    AUTO_GROUND_TRUTH_SPOT_CHECK_RATE: float = 0.10  # 10% Stichproben-Review
    AUTO_GROUND_TRUTH_TASK_DELAY_SECONDS: int = 3  # Delay after OCR before ground-truth task

    # Performance (Worker-Konfiguration)
    WORKER_CONNECTIONS: int = 1000
    KEEPALIVE_TIMEOUT: int = 5
    # DB Pool Settings sind oben bei "Database Connection Pool Settings" definiert
    
    # Monitoring
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090

    # Grafana Integration
    GRAFANA_URL: str = Field(
        default="http://localhost:3000",
        description="Grafana Dashboard Base URL"
    )
    GRAFANA_ENABLED: bool = Field(
        default=True,
        description="Grafana Dashboard Links aktivieren"
    )

    # Prometheus Metrics Scraping
    # Token für interne Metrics-Endpoints (Prometheus, Grafana)
    # Generieren: python -c "import secrets; print(secrets.token_urlsafe(32))"
    METRICS_SCRAPE_TOKEN: Optional[str] = Field(
        default=None,
        description="Token für Prometheus/Grafana Metrics-Scraping (wenn gesetzt, /internal/metrics erfordert diesen Token)"
    )

    # Email (optional, for notifications)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[SecretStr] = None
    SMTP_FROM_EMAIL: Optional[str] = "noreply@ablage-system.local"
    SMTP_TLS: bool = True

    # =============================================================================
    # Slack Integration
    # =============================================================================
    # Webhook-URL: Erstellen unter https://api.slack.com/apps -> Incoming Webhooks
    SLACK_WEBHOOK_URL: Optional[SecretStr] = Field(
        default=None,
        description="Slack Incoming Webhook URL für Benachrichtigungen"
    )
    # Bot Token: Erstellen unter https://api.slack.com/apps -> OAuth & Permissions
    # Scopes: chat:write, files:write, users:read
    SLACK_BOT_TOKEN: Optional[SecretStr] = Field(
        default=None,
        description="Slack Bot OAuth Token (xoxb-...) für erweiterte Funktionen"
    )
    # Standard-Kanal für Benachrichtigungen (ohne #)
    SLACK_DEFAULT_CHANNEL: str = Field(
        default="ablage-notifications",
        description="Standard-Slack-Kanal für Benachrichtigungen"
    )
    # Aktivierung der Slack-Integration
    SLACK_ENABLED: bool = Field(
        default=False,
        description="Slack-Integration aktivieren"
    )
    # Notification-Typen die an Slack gesendet werden
    SLACK_NOTIFICATION_TYPES: List[str] = Field(
        default_factory=lambda: [
            "document_processed",
            "document_error",
            "approval_required",
            "approval_completed",
            "workflow_completed",
            "high_risk_entity",
            "dunning_escalation",
        ],
        description="Notification-Typen die an Slack weitergeleitet werden"
    )
    # Rate Limiting für Slack (max Nachrichten pro Minute)
    SLACK_RATE_LIMIT_PER_MINUTE: int = Field(
        default=30,
        ge=1, le=100,
        description="Maximale Slack-Nachrichten pro Minute"
    )

    # =============================================================================
    # Microsoft Teams Integration
    # =============================================================================
    # Webhook-URL: Erstellen in Teams-Kanal -> Connectors -> Incoming Webhook
    # Oder via Power Automate: https://flow.microsoft.com
    TEAMS_WEBHOOK_URL: Optional[SecretStr] = Field(
        default=None,
        description="Microsoft Teams Incoming Webhook URL für Benachrichtigungen"
    )
    # Standard-Kanal Name (nur für Logging/Anzeige, nicht für Routing)
    TEAMS_DEFAULT_CHANNEL: Optional[str] = Field(
        default=None,
        description="Standard-Teams-Kanal Name (für Anzeige)"
    )
    # Aktivierung der Teams-Integration
    TEAMS_ENABLED: bool = Field(
        default=False,
        description="Microsoft Teams-Integration aktivieren"
    )
    # Notification-Typen die an Teams gesendet werden
    TEAMS_NOTIFICATION_TYPES: List[str] = Field(
        default_factory=lambda: [
            "document_processed",
            "document_error",
            "approval_required",
            "approval_completed",
            "workflow_completed",
            "high_risk_entity",
            "dunning_escalation",
            "payment_reminder",
            "system_alert",
            "error_notification",
        ],
        description="Notification-Typen die an Teams weitergeleitet werden"
    )
    # Rate Limiting für Teams (max Nachrichten pro Minute)
    TEAMS_RATE_LIMIT_PER_MINUTE: int = Field(
        default=30,
        ge=1, le=100,
        description="Maximale Teams-Nachrichten pro Minute"
    )

    # =============================================================================
    # Twilio SMS/WhatsApp Integration
    # =============================================================================
    # Account SID und Auth Token: Erstellen unter https://console.twilio.com
    TWILIO_ACCOUNT_SID: Optional[str] = Field(
        default=None,
        description="Twilio Account SID"
    )
    TWILIO_AUTH_TOKEN: Optional[SecretStr] = Field(
        default=None,
        description="Twilio Auth Token"
    )
    # Telefonnummern für SMS und WhatsApp
    TWILIO_PHONE_NUMBER: Optional[str] = Field(
        default=None,
        description="Twilio Absender-Telefonnummer (E.164 Format: +49...)"
    )
    TWILIO_WHATSAPP_NUMBER: Optional[str] = Field(
        default=None,
        description="Twilio WhatsApp-Nummer (Format: whatsapp:+14155238886)"
    )
    # Feature-Flags
    TWILIO_ENABLED: bool = Field(
        default=False,
        description="Twilio SMS/WhatsApp Integration aktivieren"
    )
    # Budget-Schutz: Maximale SMS pro Tag
    TWILIO_MAX_SMS_PER_DAY: int = Field(
        default=100,
        ge=1, le=1000,
        description="Maximale SMS pro Tag (Budget-Schutz)"
    )
    # Budget-Schutz: Maximales monatliches Budget in EUR
    TWILIO_MAX_MONTHLY_BUDGET_EUR: float = Field(
        default=50.0,
        ge=1.0, le=1000.0,
        description="Maximales monatliches Twilio-Budget in EUR"
    )
    # Notification-Typen die SMS ausloesen (nur kritische)
    TWILIO_SMS_NOTIFICATION_TYPES: List[str] = Field(
        default_factory=lambda: [
            "critical_alert",
            "fraud_detected",
            "security_incident",
            "system_down",
            "escalation",
        ],
        description="Notification-Typen die SMS ausloesen"
    )

    # Development
    TESTING: bool = False

    # Vault Configuration
    VAULT_ENABLED: bool = False  # Enable Vault integration
    VAULT_ADDR: Optional[str] = None  # Vault server address
    VAULT_TOKEN: Optional[str] = None  # Vault token
    VAULT_ROLE_ID: Optional[str] = None  # AppRole role ID
    VAULT_SECRET_ID: Optional[str] = None  # AppRole secret ID
    VAULT_NAMESPACE: Optional[str] = None  # Vault namespace (Enterprise)
    VAULT_SECRET_PATH: str = "ablage-system"  # Path to secrets in Vault
    VAULT_MOUNT_POINT: str = "secret"  # KV mount point
    VAULT_VERIFY_SSL: bool = True  # Verify Vault SSL
    VAULT_SECRET_REFRESH_INTERVAL: int = 300  # Refresh secrets every 5 minutes

    # =============================================================================
    # Translation Settings (für mehrsprachige Dokumentenextraktion)
    # =============================================================================
    # Provider: "argos" (offline, empfohlen), "libretranslate" (self-hosted), "deepl" (cloud), "disabled"
    TRANSLATION_PROVIDER: str = "argos"
    TRANSLATION_TARGET_LANGUAGE: str = "de"  # Zielsprache für Extraktion
    TRANSLATION_CACHE_ENABLED: bool = True  # Übersetzungen cachen

    # LibreTranslate (self-hosted) - nur wenn TRANSLATION_PROVIDER="libretranslate"
    LIBRETRANSLATE_URL: Optional[str] = "http://localhost:5000"

    # DeepL API (kostenpflichtig) - nur wenn TRANSLATION_PROVIDER="deepl"
    DEEPL_API_KEY: Optional[SecretStr] = None

    # =============================================================================
    # RAG Intelligence Layer Settings
    # =============================================================================
    # Document Chunking
    RAG_CHUNK_SIZE: int = 512  # Default Tokens pro Chunk
    RAG_CHUNK_OVERLAP: int = 50  # Überlappung zwischen Chunks
    RAG_CHUNK_MIN_SIZE: int = 100  # Minimum Chunk-Größe
    RAG_CHUNK_MAX_SIZE: int = 2048  # Maximum Chunk-Größe
    RAG_CHUNKING_STRATEGY: str = "semantic"  # semantic, fixed, document_type

    # LLM Inference (Ollama)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_TIMEOUT: int = 120  # Timeout in Sekunden
    OLLAMA_KEEP_ALIVE: str = "24h"  # Modell im Speicher halten
    DEFAULT_LLM_REALTIME: str = "qwen2.5:7b"  # Für schnelle Antworten (<15s)
    DEFAULT_LLM_ANALYSIS: str = "qwen2.5:14b"  # Für detaillierte Analyse
    LLM_MAX_CONCURRENT_REQUESTS: int = 4

    # RAG Search
    RAG_SEARCH_DEFAULT_LIMIT: int = 20
    RAG_SEARCH_MAX_LIMIT: int = 100
    RAG_SEMANTIC_THRESHOLD: float = 0.7  # Minimum Cosine Similarity
    RAG_RERANK_ENABLED: bool = True
    RAG_RERANK_TOP_K: int = 10

    # =============================================================================
    # Conversational Assistant (Chat mit Ollama)
    # =============================================================================
    ASSISTANT_ENABLED: bool = Field(
        default=True,
        description="Conversational Assistant aktivieren"
    )
    ASSISTANT_MAX_CONTEXT_DOCS: int = Field(
        default=5,
        ge=1, le=20,
        description="Maximale Anzahl Dokumente für RAG-Kontext"
    )
    ASSISTANT_OLLAMA_MODEL: str = Field(
        default="llama3.1",
        description="Ollama-Modell für Conversational Assistant"
    )
    ASSISTANT_TEMPERATURE: float = Field(
        default=0.3,
        ge=0.0, le=2.0,
        description="Temperatur für LLM-Antworten (0=deterministisch, 2=kreativ)"
    )
    ASSISTANT_MAX_HISTORY: int = Field(
        default=50,
        ge=10, le=200,
        description="Maximale Anzahl Nachrichten pro Session"
    )
    ASSISTANT_SESSION_EXPIRY_DAYS: int = Field(
        default=30,
        ge=1, le=365,
        description="Tage bis Session-Archivierung"
    )

    # =============================================================================
    # E-Invoice Settings (ZUGFeRD / XRechnung)
    # =============================================================================
    # Mustang Microservice für XRechnung UBL und KoSIT-Validierung
    MUSTANG_SERVICE_URL: str = Field(
        default="http://einvoice-mustang:8091",
        description="URL des Mustang E-Invoice Microservices"
    )
    MUSTANG_SERVICE_TIMEOUT: int = Field(
        default=60,
        ge=10, le=300,
        description="Timeout für Mustang-Anfragen in Sekunden"
    )
    EINVOICE_TEMP_DIR: Path = Field(
        default=Path("/app/temp/einvoice"),
        description="Temporaeres Verzeichnis für E-Invoice Verarbeitung"
    )

    # Reranker Dual-Stack Configuration (GPU + CPU Fallback)
    # GPU: BGE-Reranker-v2-m3 (~1GB VRAM, multilingual)
    # CPU: MiniLM Cross-Encoder (~300MB RAM, fallback)
    RERANKER_GPU_MODEL: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="GPU Reranker Modell (Cross-Encoder)"
    )
    RERANKER_CPU_MODEL: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-12-v2",
        description="CPU Fallback Reranker Modell"
    )
    RERANKER_BATCH_SIZE: int = Field(
        default=8,
        ge=1, le=64,
        description="Batch-Größe für Reranking"
    )
    RERANKER_MAX_LENGTH: int = Field(
        default=512,
        ge=64, le=1024,
        description="Max Token-Länge pro Dokument"
    )
    RERANKER_GPU_VRAM_GB: float = Field(
        default=1.0,
        description="Erwarteter VRAM-Verbrauch des GPU-Rerankers in GB"
    )
    RERANKER_PREFER_GPU: bool = Field(
        default=True,
        description="GPU bevorzugen wenn verfügbar"
    )
    # Legacy: Externer HTTP-Service (optional, für Kompatibilität)
    RERANKER_SERVICE_URL: Optional[str] = Field(
        default=None,
        description="Optionaler externer Reranker Service (nicht empfohlen)"
    )
    RERANKER_TIMEOUT: int = 30

    # Customer Cards
    RAG_CUSTOMER_CARD_CACHE_TTL: int = 3600  # 1 Stunde
    RAG_CUSTOMER_CARD_SYNC_CRON: str = "0 3 * * *"  # Täglich 03:00 Uhr
    RAG_CUSTOMER_CARD_BATCH_SIZE: int = 50
    RAG_CUSTOMER_CARD_CONTEXT_CHUNKS: int = 10  # Anzahl Chunks für Card-Generierung

    # Chat
    RAG_CHAT_MAX_HISTORY: int = 20  # Maximale Anzahl Nachrichten pro Session
    RAG_CHAT_CONTEXT_CHUNKS: int = 5  # Anzahl Kontext-Chunks pro Anfrage

    # Batch Jobs
    RAG_BATCH_JOB_MAX_RETRIES: int = 3
    RAG_BATCH_JOB_RETRY_DELAY: int = 60  # Sekunden

    # =============================================================================
    # KI-Autonomie Settings (Confidence-basierte Auto-Aktionen)
    # =============================================================================
    # Bei Confidence >= Threshold führt das System automatisch Aktionen aus
    # ohne User-Interaktion. Darunter wird User-Bestätiuung angefordert.

    # Auto-Classification: Dokumente automatisch klassifizieren
    AUTONOMY_DOCUMENT_CLASSIFICATION_THRESHOLD: float = Field(
        default=0.95,
        ge=0.5, le=1.0,
        description="Confidence-Threshold für automatische Dokumentenklassifizierung"
    )

    # Auto-Entity-Linking: Dokumente automatisch mit Entities verknüpfen
    AUTONOMY_ENTITY_LINKING_THRESHOLD: float = Field(
        default=0.90,
        ge=0.5, le=1.0,
        description="Confidence-Threshold für automatisches Entity-Linking"
    )

    # Auto-Invoice-Approval: Rechnungen automatisch freigeben
    AUTONOMY_INVOICE_APPROVAL_THRESHOLD: float = Field(
        default=0.95,
        ge=0.5, le=1.0,
        description="Confidence-Threshold für automatische Rechnungsfreigabe"
    )

    # Auto-Payment-Matching: Zahlungen automatisch zuordnen
    AUTONOMY_PAYMENT_MATCHING_THRESHOLD: float = Field(
        default=0.95,
        ge=0.5, le=1.0,
        description="Confidence-Threshold für automatische Zahlungszuordnung"
    )

    # Auto-OCR-Correction: OCR-Ergebnisse automatisch korrigieren
    AUTONOMY_OCR_CORRECTION_THRESHOLD: float = Field(
        default=0.90,
        ge=0.5, le=1.0,
        description="Confidence-Threshold für automatische OCR-Korrekturen"
    )

    # Auto-Approval Limits (zusätzlich zu Confidence)
    AUTONOMY_AUTO_APPROVAL_MAX_AMOUNT: float = Field(
        default=5000.0,
        ge=0.0,
        description="Maximaler Betrag (EUR) für automatische Rechnungsfreigabe"
    )
    AUTONOMY_AUTO_APPROVAL_ENABLED: bool = Field(
        default=True,
        description="Automatische Rechnungsfreigabe aktivieren"
    )

    # Routing Intelligence: Automatisches Dokumenten-Routing
    AUTONOMY_ROUTING_ENABLED: bool = Field(
        default=True,
        description="KI-basiertes Dokumenten-Routing aktivieren"
    )
    AUTONOMY_ROUTING_MIN_CONFIDENCE: float = Field(
        default=0.85,
        ge=0.5, le=1.0,
        description="Minimale Confidence für automatisches Routing"
    )

    # Anomalie-Erkennung: Automatische Alerts
    AUTONOMY_ANOMALY_DETECTION_ENABLED: bool = Field(
        default=True,
        description="Automatische Anomalie-Erkennung aktivieren"
    )
    AUTONOMY_ANOMALY_ALERT_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0, le=1.0,
        description="Anomalie-Score ab dem Alerts generiert werden"
    )

    # Smart Suggestions: Vorschläge für User
    AUTONOMY_SUGGESTIONS_ENABLED: bool = Field(
        default=True,
        description="Smart Suggestions aktivieren"
    )
    AUTONOMY_MAX_SUGGESTIONS_PER_DOCUMENT: int = Field(
        default=5,
        ge=1, le=20,
        description="Maximale Anzahl Vorschläge pro Dokument"
    )

    # Natural Language Queries: NLQ aktivieren
    AUTONOMY_NLQ_ENABLED: bool = Field(
        default=True,
        description="Natural Language Queries aktivieren"
    )
    AUTONOMY_NLQ_MAX_RESULTS: int = Field(
        default=100,
        ge=10, le=500,
        description="Maximale Ergebnisse pro NLQ-Abfrage"
    )

    # Logging von autonomen Aktionen
    AUTONOMY_AUDIT_LOGGING_ENABLED: bool = Field(
        default=True,
        description="Alle autonomen Aktionen im Audit-Log protokollieren"
    )

    # =============================================================================
    # Tune Settings (Dokument-Kontext-Konfiguration)
    # =============================================================================
    # Tunes definieren kontextspezifische Verarbeitungsregeln für Dokumente
    # z.B. "Rechnungen", "Verträge", "Allgemeiner Schriftverkehr"

    # Tune-Name Limits
    TUNE_NAME_MIN_LENGTH: int = Field(default=1, ge=1, description="Minimale Länge des Tune-Namens")
    TUNE_NAME_MAX_LENGTH: int = Field(default=100, ge=10, description="Maximale Länge des Tune-Namens")
    TUNE_DESCRIPTION_MAX_LENGTH: int = Field(default=500, ge=50, description="Maximale Länge der Beschreibung")

    # Prompt-Template Settings
    TUNE_PROMPT_TEMPLATE_MAX_LENGTH: int = Field(
        default=10000,
        ge=100,
        description="Maximale Länge des Prompt-Templates in Zeichen"
    )
    TUNE_PROMPT_TEMPLATE_REQUIRED: bool = Field(
        default=False,
        description="Ob ein Prompt-Template für neue Tunes erforderlich ist"
    )

    # Caching
    TUNE_CACHE_ENABLED: bool = Field(default=True, description="Tune-Caching aktivieren")
    TUNE_CACHE_TTL: int = Field(default=3600, ge=60, description="Cache-TTL für Tunes in Sekunden")
    TUNE_LIST_CACHE_TTL: int = Field(default=300, ge=30, description="Cache-TTL für Tune-Liste in Sekunden")

    # Defaults für neue Tunes
    TUNE_DEFAULT_ICON: str = Field(default="FileText", description="Standard-Icon für neue Tunes (Lucide)")
    TUNE_DEFAULT_COLOR: str = Field(default="bg-slate-500", description="Standard-Farbe für neue Tunes (Tailwind)")
    TUNE_DEFAULT_BACKEND: Optional[str] = Field(default=None, description="Standard-OCR-Backend (None = auto)")

    # System-Tunes (können nicht gelöscht werden)
    TUNE_SYSTEM_PROTECTED: bool = Field(
        default=True,
        description="System-Tunes vor Löschung schützen"
    )

    # Rate Limiting für Tune-API
    TUNE_API_RATE_LIMIT_ENABLED: bool = Field(default=True, description="Rate Limiting für Tune-API aktivieren")
    TUNE_API_REQUESTS_PER_MINUTE: int = Field(default=60, ge=1, description="Max Requests pro Minute für Tune-API")

    # Pagination Defaults
    TUNE_LIST_DEFAULT_LIMIT: int = Field(default=100, ge=10, description="Standard-Limit für Tune-Liste")
    TUNE_LIST_MAX_LIMIT: int = Field(default=500, ge=100, description="Maximales Limit für Tune-Liste")

    # =============================================================================
    # FinTS / Banking Auto-Sync (Remediation-Strom G4)
    # =============================================================================
    # Guard, ob der FinTS-Mock-Sync echte Reconciliation/Buchung ausloesen darf.
    # Default False: Der Mock-Sync laeuft im reinen Trockenlauf (keine echten
    # Buchungen/Abgleiche), solange dieser Schalter nicht explizit aktiviert wird.
    # G4 (Bank-Sync-Service) liest diesen Wert vor jeder schreibenden Aktion.
    FINTS_ALLOW_MOCK_SYNC: bool = Field(
        default=False,
        description="Erlaubt dem FinTS-Mock-Sync, echte Reconciliation/Buchung auszuloesen (Default: nur Trockenlauf)"
    )
    # Ob der automatische Bank-Sync-Beat (periodischer Celery-Beat-Task) aktiv ist.
    # Default False: Kein automatischer Sync, bis bewusst aktiviert.
    FINTS_AUTO_SYNC_ENABLED: bool = Field(
        default=False,
        description="Aktiviert den automatischen Bank-Sync-Beat (periodischer FinTS-Abgleich)"
    )

    @model_validator(mode='after')
    def build_computed_urls(self) -> 'Settings':
        """Build database and Redis URLs from components if not provided."""
        # ========== Q.2 SECURITY FIX: DEBUG Mode in Production verhindern ==========
        if self.DEBUG and self.ENVIRONMENT.lower() in ("production", "prod"):
            raise ValueError(
                "KRITISCHER SICHERHEITSFEHLER: DEBUG=True ist in Production nicht erlaubt! "
                "Setze DEBUG=False oder ändere ENVIRONMENT auf 'development'. "
                "DEBUG in Production kann zu Information Leakage und CORS-Problemen führen."
            )

        # ========== SECRET_KEY Validierung ==========
        # In Production: SECRET_KEY MUSS explizit gesetzt sein
        # In Development: Generiere temporären Key mit Warnung
        # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
        secret_key_value = self.SECRET_KEY.get_secret_value() if isinstance(self.SECRET_KEY, SecretStr) else self.SECRET_KEY
        if not secret_key_value:
            if not self.DEBUG:
                raise ValueError(
                    "SECRET_KEY ist nicht gesetzt! "
                    "In Production muss SECRET_KEY via Umgebungsvariable definiert werden. "
                    "Generiere einen sicheren Key mit: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
            else:
                # Development: Generiere temporären Key mit Warnung
                temp_key = secrets.token_urlsafe(64)
                logger.warning(
                    "secret_key_auto_generated",
                    message="SECRET_KEY wurde automatisch generiert! "
                            "In Production muss ein persistenter Key gesetzt werden. "
                            "Alle JWTs werden nach App-Neustart ungültig!",
                    key_length=len(temp_key)
                )
                object.__setattr__(self, 'SECRET_KEY', SecretStr(temp_key))
        elif len(secret_key_value) < 32:
            raise ValueError(
                f"SECRET_KEY ist zu kurz ({len(secret_key_value)} Zeichen). "
                "Mindestens 32 Zeichen erforderlich für sichere JWT-Signierung."
            )
        else:
            # Entropie-Validierung nur in Production
            if not self.DEBUG:
                is_valid, error_msg = validate_secret_entropy(
                    secret_key_value,
                    min_entropy_bits=128.0,  # AES-128 Sicherheit
                    min_unique_ratio=0.25    # 25% einzigartige Zeichen
                )
                if not is_valid:
                    raise ValueError(f"SECRET_KEY unsicher: {error_msg}")

                entropy = calculate_entropy_bits(secret_key_value)
                logger.info(
                    "secret_key_validated",
                    entropy_bits=round(entropy, 1),
                    length=len(secret_key_value)
                )

        # ========== CORS Origins Validierung ==========
        # In Production: Keine localhost Origins erlauben
        localhost_patterns = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        has_localhost = any(
            any(pattern in origin.lower() for pattern in localhost_patterns)
            for origin in self.CORS_ORIGINS
        )
        has_wildcard = "*" in self.CORS_ORIGINS

        if has_wildcard:
            if self.CORS_ALLOW_CREDENTIALS:
                raise ValueError(
                    "CORS_ORIGINS='*' ist nicht erlaubt wenn CORS_ALLOW_CREDENTIALS=True! "
                    "Setze explizite Origins oder deaktiviere Credentials."
                )
            if not self.DEBUG:
                raise ValueError(
                    "CORS_ORIGINS='*' ist in Production nicht erlaubt! "
                    "Setze explizite Origins via CORS_ORIGINS Umgebungsvariable."
                )

        if has_localhost and not self.DEBUG:
            raise ValueError(
                "CORS_ORIGINS enthält localhost-Adressen in Production! "
                "Entferne localhost aus CORS_ORIGINS oder setze DEBUG=True. "
                f"Gefundene Origins: {self.CORS_ORIGINS}"
            )
        elif has_localhost and self.DEBUG:
            logger.warning(
                "cors_localhost_origins_in_development",
                message="localhost in CORS Origins nur für Development verwenden!",
                origins=self.CORS_ORIGINS
            )
            # SECURITY: Zusätzliche Warnung wenn Credentials mit localhost erlaubt sind
            if self.CORS_ALLOW_CREDENTIALS:
                logger.warning(
                    "cors_localhost_with_credentials",
                    message="CORS: localhost Origins mit CORS_ALLOW_CREDENTIALS=true ist ein Sicherheitsrisiko! "
                            "XSS-Angriffe auf localhost könnten Credentials stehlen.",
                    origins=self.CORS_ORIGINS,
                    hint="Setze CORS_ALLOW_CREDENTIALS=false für Development oder verwende explizite Origins."
                )

        # Production: Nur HTTPS Origins erlauben (außer für localhost in DEBUG)
        if not self.DEBUG and self.CORS_ORIGINS:
            non_https_origins = [
                origin for origin in self.CORS_ORIGINS
                if origin != "*" and not origin.startswith("https://")
            ]
            if non_https_origins:
                raise ValueError(
                    "CORS_ORIGINS enthält nicht-HTTPS Origins in Production! "
                    "Alle Origins müssen HTTPS verwenden. "
                    f"Gefundene HTTP Origins: {non_https_origins}"
                )

        # Validiere Origin-Format (muss valide URL sein)
        invalid_origins = []
        for origin in self.CORS_ORIGINS:
            if origin == "*":
                continue
            # Muss mit http:// oder https:// beginnen
            if not origin.startswith(("http://", "https://")):
                invalid_origins.append(origin)
            # Darf keinen Pfad enthalten (außer root /)
            from urllib.parse import urlparse
            try:
                parsed = urlparse(origin)
                if parsed.path and parsed.path != "/" and parsed.path != "":
                    invalid_origins.append(f"{origin} (hat Pfad: {parsed.path})")
            except Exception:
                invalid_origins.append(f"{origin} (ungültige URL)")

        if invalid_origins:
            raise ValueError(
                "CORS_ORIGINS enthält ungültige Origins! "
                "Origins müssen mit http:// oder https:// beginnen und keinen Pfad enthalten. "
                f"Ungültige Origins: {invalid_origins}"
            )

        # ========== Infrastruktur-Validierung (Production) ==========
        if not self.DEBUG:
            # Kritische Services dürfen nicht auf localhost zeigen in Production
            localhost_hosts = ("localhost", "127.0.0.1", "::1")

            infrastructure_warnings = []

            if self.DB_HOST in localhost_hosts:
                infrastructure_warnings.append(f"DB_HOST={self.DB_HOST}")

            # Check DB SSL configuration in Production
            if self.DB_SSL_MODE in ("disable", "allow"):
                infrastructure_warnings.append(
                    f"DB_SSL_MODE={self.DB_SSL_MODE} in Production! "
                    "Datenbankverbindungen sind unverschluesselt oder unsicher. "
                    "Setze DB_SSL_MODE=require oder höher."
                )

            if self.REDIS_HOST in localhost_hosts:
                infrastructure_warnings.append(f"REDIS_HOST={self.REDIS_HOST}")

            if any(host in self.MINIO_ENDPOINT for host in localhost_hosts):
                infrastructure_warnings.append(f"MINIO_ENDPOINT={self.MINIO_ENDPOINT}")

            if infrastructure_warnings:
                logger.warning(
                    "production_localhost_infrastructure",
                    message="Kritische Services zeigen auf localhost in Production!",
                    services=infrastructure_warnings,
                    hint="Setze DEBUG=True für Development oder konfiguriere echte Hosts."
                )

            # Prüfe auf Default-Passwörter in Production
            default_passwords = ["changeme", "postgres", "password", "secret", "admin"]

            db_password = self.DB_PASSWORD.get_secret_value() if self.DB_PASSWORD else ""
            if db_password.lower() in default_passwords:
                raise ValueError(
                    "DB_PASSWORD verwendet ein unsicheres Default-Passwort in Production! "
                    "Bitte setze ein starkes Passwort."
                )

            # Prüfe MinIO Default-Credentials (SECURITY FIX: Error statt Warning)
            minio_secret = self.MINIO_SECRET_KEY.get_secret_value() if self.MINIO_SECRET_KEY else ""
            minio_default_users = ["minioadmin", "admin", "minio", "root"]
            minio_default_passwords = ["minioadmin", "minioadmin123", "minio123", "admin", "password", "123456"]

            if self.MINIO_ACCESS_KEY.lower() in minio_default_users:
                raise ValueError(
                    f"MINIO_ACCESS_KEY '{self.MINIO_ACCESS_KEY}' ist ein unsicherer Default-Wert in Production! "
                    "Bitte setze einen eindeutigen Access Key mit mindestens 8 Zeichen."
                )

            if minio_secret.lower() in minio_default_passwords:
                raise ValueError(
                    "MINIO_SECRET_KEY verwendet ein unsicheres Default-Passwort in Production! "
                    "Bitte setze ein starkes Secret Key mit mindestens 12 Zeichen."
                )

            # Prüfe MinIO Secret Key Komplexität (min 12 Zeichen für Production)
            if len(minio_secret) < 12:
                raise ValueError(
                    f"MINIO_SECRET_KEY ist zu kurz ({len(minio_secret)} Zeichen). "
                    "In Production sind mindestens 12 Zeichen erforderlich."
                )

            # Prüfe MinIO Access Key Länge (min 8 Zeichen)
            if len(self.MINIO_ACCESS_KEY) < 8:
                raise ValueError(
                    f"MINIO_ACCESS_KEY ist zu kurz ({len(self.MINIO_ACCESS_KEY)} Zeichen). "
                    "In Production sind mindestens 8 Zeichen erforderlich."
                )

        # ========== Rate Limit Tier Validierung ==========
        # Daily limits müssen >= Hourly limits sein
        if self.RATE_LIMIT_FREE_DAILY < self.RATE_LIMIT_FREE_HOURLY:
            raise ValueError(
                f"RATE_LIMIT_FREE_DAILY ({self.RATE_LIMIT_FREE_DAILY}) muss >= "
                f"RATE_LIMIT_FREE_HOURLY ({self.RATE_LIMIT_FREE_HOURLY}) sein!"
            )
        if self.RATE_LIMIT_PREMIUM_DAILY < self.RATE_LIMIT_PREMIUM_HOURLY:
            raise ValueError(
                f"RATE_LIMIT_PREMIUM_DAILY ({self.RATE_LIMIT_PREMIUM_DAILY}) muss >= "
                f"RATE_LIMIT_PREMIUM_HOURLY ({self.RATE_LIMIT_PREMIUM_HOURLY}) sein!"
            )

        # ========== Vault Konfiguration Validierung ==========
        if self.VAULT_ENABLED:
            # Wenn Vault aktiviert ist, müssen Authentifizierungs-Credentials gesetzt sein
            has_token = bool(self.VAULT_TOKEN)
            has_approle = bool(self.VAULT_ROLE_ID and self.VAULT_SECRET_ID)

            if not has_token and not has_approle:
                raise ValueError(
                    "VAULT_ENABLED=True aber keine Authentifizierung konfiguriert! "
                    "Setze entweder VAULT_TOKEN oder beide VAULT_ROLE_ID und VAULT_SECRET_ID."
                )

            if not self.VAULT_ADDR:
                raise ValueError(
                    "VAULT_ENABLED=True aber VAULT_ADDR ist nicht gesetzt! "
                    "Setze die Vault Server-Adresse (z.B. https://vault.example.com:8200)."
                )

            # Production: HTTPS für Vault erzwingen
            if not self.DEBUG and self.VAULT_ADDR and not self.VAULT_ADDR.startswith("https://"):
                raise ValueError(
                    f"VAULT_ADDR '{self.VAULT_ADDR}' verwendet kein HTTPS in Production! "
                    "Vault-Verbindungen müssen in Production verschluesselt sein."
                )

            logger.info(
                "vault_configuration_validated",
                vault_addr=self.VAULT_ADDR,
                auth_method="token" if has_token else "approle",
                verify_ssl=self.VAULT_VERIFY_SSL
            )
        else:
            # SECURITY: In Production sollte Vault verwendet werden
            if not self.DEBUG:
                logger.critical(
                    "vault_disabled_in_production",
                    message="VAULT_ENABLED=False in Production! "
                            "Secrets werden aus Umgebungsvariablen gelesen. "
                            "Für bessere Sicherheit empfehlen wir Vault zu aktivieren.",
                    hint="Setze VAULT_ENABLED=true und konfiguriere Vault-Credentials.",
                    action_required=True
                )

        # ========== DB SSL Mode Validierung ==========
        if self.ENVIRONMENT != "development" and self.DB_SSL_MODE in ("disable", "allow", "prefer"):
            logger.warning(
                "db_ssl_mode_unsicher",
                ssl_mode=self.DB_SSL_MODE,
                message=f"DB_SSL_MODE='{self.DB_SSL_MODE}' ist in Production unsicher! "
                        "Empfohlen: 'require', 'verify-ca' oder 'verify-full'.",
                action_required=True,
            )

        # ========== DB SSL Zertifikat-Pfade Validierung ==========
        ssl_cert_fields = {
            "DB_SSL_CERT": self.DB_SSL_CERT,
            "DB_SSL_KEY": self.DB_SSL_KEY,
            "DB_SSL_ROOT_CERT": self.DB_SSL_ROOT_CERT,
        }
        for field_name, cert_path in ssl_cert_fields.items():
            if cert_path is not None:
                cert_file = Path(cert_path)
                if not cert_file.exists():
                    raise ValueError(
                        f"{field_name}='{cert_path}' existiert nicht! "
                        f"Stelle sicher, dass die SSL-Zertifikatsdatei unter dem angegebenen Pfad liegt."
                    )
                if not cert_file.is_file():
                    raise ValueError(
                        f"{field_name}='{cert_path}' ist keine Datei! "
                        f"Erwartet wird ein Pfad zu einer SSL-Zertifikatsdatei."
                    )

        # ========== ENCRYPTION_KEY Validierung ==========
        # In Production: ENCRYPTION_KEY sollte explizit gesetzt sein für TOTP-Secrets
        if not self.DEBUG:
            encryption_key_value = self.ENCRYPTION_KEY.get_secret_value() if self.ENCRYPTION_KEY else None
            if not encryption_key_value:
                logger.warning(
                    "encryption_key_not_set_production",
                    message="ENCRYPTION_KEY ist nicht gesetzt in Production! "
                            "TOTP-Secrets und andere sensible Daten werden mit abgeleitetem Key verschlüsselt. "
                            "Für maximale Sicherheit setze einen expliziten ENCRYPTION_KEY.",
                    hint="Generiere mit: python -c \"import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
                )
            elif len(encryption_key_value) < 32:
                raise ValueError(
                    f"ENCRYPTION_KEY ist zu kurz ({len(encryption_key_value)} Zeichen). "
                    "Mindestens 32 Zeichen (Base64-encoded 32 Bytes) erforderlich für AES-256."
                )
            else:
                logger.info(
                    "encryption_key_validated",
                    key_length=len(encryption_key_value),
                    message="ENCRYPTION_KEY für TOTP-Secrets validiert"
                )

        # ========== QDRANT_API_KEY Validierung (Production) ==========
        # SECURITY FIX: Qdrant ohne API-Key erlaubt unauthentifizierten Zugriff auf Vektordaten
        if self.QDRANT_ENABLED and not self.DEBUG:
            qdrant_api_key = self.QDRANT_API_KEY.get_secret_value() if self.QDRANT_API_KEY else None
            if not qdrant_api_key:
                raise ValueError(
                    "QDRANT_API_KEY ist nicht gesetzt aber QDRANT_ENABLED=True in Production! "
                    "Qdrant ohne API-Key erlaubt unauthentifizierten Zugriff auf alle Vektordaten. "
                    "Generiere einen API-Key mit: openssl rand -hex 32 "
                    "und setze ihn in .env und docker-compose.yml."
                )
            elif len(qdrant_api_key) < 32:
                raise ValueError(
                    f"QDRANT_API_KEY ist zu kurz ({len(qdrant_api_key)} Zeichen). "
                    "Mindestens 32 Zeichen erforderlich für sichere Authentifizierung."
                )
            else:
                logger.info(
                    "qdrant_api_key_validated",
                    key_length=len(qdrant_api_key),
                    message="QDRANT_API_KEY validiert - Qdrant authentifiziert"
                )
        elif self.QDRANT_ENABLED and self.DEBUG:
            # Development: Warnung wenn kein API-Key gesetzt
            qdrant_api_key = self.QDRANT_API_KEY.get_secret_value() if self.QDRANT_API_KEY else None
            if not qdrant_api_key:
                logger.warning(
                    "qdrant_no_api_key_development",
                    message="QDRANT_API_KEY nicht gesetzt in Development - Qdrant laeuft ohne Authentifizierung! "
                            "In Production ist ein API-Key PFLICHT.",
                    hint="Generiere mit: openssl rand -hex 32"
                )

        # Build DATABASE_URL if not set
        if not self.DATABASE_URL:
            password = self.DB_PASSWORD
            if isinstance(password, SecretStr):
                password = password.get_secret_value()

            # Build base URL
            base_url = (
                f"postgresql+asyncpg://{self.DB_USER}:"
                f"{password}@{self.DB_HOST}:"
                f"{self.DB_PORT}/{self.DB_NAME}"
            )

            # Add SSL parameters
            ssl_params = []
            ssl_params.append(f"sslmode={self.DB_SSL_MODE}")

            if self.DB_SSL_CERT:
                ssl_params.append(f"sslcert={self.DB_SSL_CERT}")
            if self.DB_SSL_KEY:
                ssl_params.append(f"sslkey={self.DB_SSL_KEY}")
            if self.DB_SSL_ROOT_CERT:
                ssl_params.append(f"sslrootcert={self.DB_SSL_ROOT_CERT}")

            if ssl_params:
                database_url = f"{base_url}?{'&'.join(ssl_params)}"
            else:
                database_url = base_url

            object.__setattr__(self, 'DATABASE_URL', database_url)

        # Build REDIS_URL if not set
        if not self.REDIS_URL:
            password = self.REDIS_PASSWORD
            if password:
                if isinstance(password, SecretStr):
                    password = password.get_secret_value()
                auth = f":{password}@"
            else:
                auth = ""
            object.__setattr__(self, 'REDIS_URL',
                f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )

        # Build CELERY_BROKER_URL if not set
        # When Redis Sentinel is configured, use sentinel:// scheme for Celery broker
        if not self.CELERY_BROKER_URL:
            if self.REDIS_SENTINEL_HOSTS:
                password = self.REDIS_PASSWORD
                if password:
                    if isinstance(password, SecretStr):
                        password = password.get_secret_value()
                    auth = f":{password}@"
                else:
                    auth = ""
                # Build sentinel URL: sentinel://:password@host1:port1;host2:port2/db
                sentinel_hosts = ";".join(
                    f"{auth}{h.strip()}" for h in self.REDIS_SENTINEL_HOSTS.split(",")
                )
                sentinel_url = f"sentinel://{sentinel_hosts}/{self.REDIS_DB}"
                object.__setattr__(self, 'CELERY_BROKER_URL', sentinel_url)
            else:
                object.__setattr__(self, 'CELERY_BROKER_URL', self.REDIS_URL)

        # Build CELERY_RESULT_BACKEND if not set
        if not self.CELERY_RESULT_BACKEND:
            object.__setattr__(self, 'CELERY_RESULT_BACKEND', self.REDIS_URL)

        # Build RATE_LIMIT_STORAGE_URL if not set
        if not self.RATE_LIMIT_STORAGE_URL:
            object.__setattr__(self, 'RATE_LIMIT_STORAGE_URL', self.REDIS_URL)

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra fields in .env
    )

    def get_minio_client_kwargs(self) -> Dict[str, Any]:
        """Get MinIO client configuration."""
        secret = self.MINIO_SECRET_KEY
        if isinstance(secret, SecretStr):
            secret = secret.get_secret_value()
        return {
            "endpoint": self.MINIO_ENDPOINT,
            "access_key": self.MINIO_ACCESS_KEY,
            "secret_key": secret,
            "secure": self.MINIO_SECURE
        }
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Get max upload size in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def load_secrets_from_vault(self) -> bool:
        """
        Load secrets from HashiCorp Vault if enabled.

        Secrets loaded:
        - SECRET_KEY
        - DB_PASSWORD
        - REDIS_PASSWORD
        - MINIO_SECRET_KEY
        - SMTP_PASSWORD

        Returns:
            True if secrets were loaded successfully
        """
        if not self.VAULT_ENABLED:
            logger.debug("vault_disabled", message="Vault-Integration deaktiviert")
            return False

        vault = VaultClient(
            vault_addr=self.VAULT_ADDR,
            vault_token=self.VAULT_TOKEN,
            vault_role_id=self.VAULT_ROLE_ID,
            vault_secret_id=self.VAULT_SECRET_ID,
            vault_namespace=self.VAULT_NAMESPACE,
            verify_ssl=self.VAULT_VERIFY_SSL,
        )

        if not vault.connect():
            logger.warning("vault_connection_failed", message="Konnte nicht mit Vault verbinden")
            return False

        secrets_loaded = 0
        secret_mappings = {
            "secret_key": ("SECRET_KEY", str),
            "db_password": ("DB_PASSWORD", SecretStr),
            "redis_password": ("REDIS_PASSWORD", SecretStr),
            "minio_secret_key": ("MINIO_SECRET_KEY", SecretStr),
            "smtp_password": ("SMTP_PASSWORD", SecretStr),
        }

        for vault_key, (attr_name, attr_type) in secret_mappings.items():
            value = vault.get_secret(
                path=self.VAULT_SECRET_PATH,
                key=vault_key,
                mount_point=self.VAULT_MOUNT_POINT,
            )
            if value is not None:
                if attr_type == SecretStr:
                    value = SecretStr(value)
                object.__setattr__(self, attr_name, value)
                secrets_loaded += 1
                logger.debug("vault_secret_loaded", key=vault_key)

        if secrets_loaded > 0:
            # Rebuild computed URLs with new secrets
            self.build_computed_urls()
            logger.info(
                "vault_secrets_loaded",
                count=secrets_loaded,
                path=self.VAULT_SECRET_PATH,
            )

        return secrets_loaded > 0

    def refresh_secrets(self) -> bool:
        """
        Refresh secrets from Vault (for runtime rotation).

        Call this periodically to pick up rotated secrets.

        Returns:
            True if secrets were refreshed
        """
        if not self.VAULT_ENABLED:
            return False

        vault = VaultClient.get_instance()
        vault.clear_cache()
        return self.load_secrets_from_vault()


def create_settings() -> Settings:
    """
    Create and configure Settings instance.

    Loads secrets from Vault if VAULT_ENABLED is True.
    """
    settings_instance = Settings()

    # Try to load secrets from Vault
    if settings_instance.VAULT_ENABLED:
        try:
            settings_instance.load_secrets_from_vault()
        except Exception as e:
            logger.error(
                "vault_initialization_failed",
                **safe_error_log(e),
                message="Vault-Secrets konnten nicht geladen werden, verwende Umgebungsvariablen",
            )

    return settings_instance


# Create settings instance
settings = create_settings()
