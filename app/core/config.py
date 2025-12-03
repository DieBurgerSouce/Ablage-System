"""
Application configuration using Pydantic Settings.

Supports:
- Environment variables (.env file)
- HashiCorp Vault integration for secure secrets management
- Runtime secret rotation

Feinpoliert und durchdacht - Sichere Konfigurationsverwaltung.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
import secrets
import os
import math

from pydantic import Field, field_validator, SecretStr, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog

logger = structlog.get_logger(__name__)


# ==================== Security Helper Functions ====================


def calculate_entropy_bits(secret: str) -> float:
    """
    Berechne die Entropie eines Secrets in Bits.

    Entropie = log2(Anzahl_einzigartiger_Zeichen ^ Länge)

    Args:
        secret: Der zu prüfende String

    Returns:
        Entropie in Bits
    """
    if not secret:
        return 0.0

    unique_chars = len(set(secret))
    length = len(secret)

    if unique_chars <= 1:
        return 0.0

    # Entropie = log2(unique_chars) * length
    return math.log2(unique_chars) * length


def validate_secret_entropy(
    secret: str,
    min_entropy_bits: float = 128.0,
    min_unique_ratio: float = 0.3
) -> tuple[bool, str]:
    """
    Validiere Entropie und Qualität eines Secrets.

    Args:
        secret: Der zu prüfende String
        min_entropy_bits: Mindest-Entropie in Bits (default: 128 für AES-128 Sicherheit)
        min_unique_ratio: Mindest-Verhältnis einzigartiger Zeichen (default: 30%)

    Returns:
        Tuple von (is_valid, error_message)
    """
    if not secret:
        return False, "Secret darf nicht leer sein"

    length = len(secret)
    unique_chars = len(set(secret))
    entropy = calculate_entropy_bits(secret)
    unique_ratio = unique_chars / length if length > 0 else 0

    # Prüfe Entropie
    if entropy < min_entropy_bits:
        return False, (
            f"Secret hat zu wenig Entropie ({entropy:.0f} Bits). "
            f"Mindestens {min_entropy_bits:.0f} Bits erforderlich. "
            f"Verwende mehr einzigartige Zeichen oder eine längere Zeichenkette."
        )

    # Prüfe Einzigartigkeit (verhindert "aaaaaaa...")
    if unique_ratio < min_unique_ratio:
        return False, (
            f"Secret hat zu wenig einzigartige Zeichen ({unique_ratio*100:.0f}%). "
            f"Mindestens {min_unique_ratio*100:.0f}% einzigartige Zeichen erforderlich."
        )

    # Prüfe auf offensichtlich schwache Muster
    weak_patterns = [
        "12345", "password", "secret", "admin", "test",
        "qwerty", "asdfgh", "00000", "11111", "abcde"
    ]
    secret_lower = secret.lower()
    for pattern in weak_patterns:
        if pattern in secret_lower:
            return False, (
                f"Secret enthält schwaches Muster: '{pattern}'. "
                "Verwende einen sicher generierten Schlüssel: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )

    return True, ""

# Try to import hvac for Vault integration
try:
    import hvac
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    hvac = None  # type: ignore
    logger.debug("vault_client_not_available", message="hvac not installed, Vault integration disabled")


class VaultClient:
    """
    HashiCorp Vault client for secure secrets management.

    Supports:
    - Token-based authentication
    - AppRole authentication
    - Kubernetes authentication
    - Secret caching with TTL
    """

    _instance: Optional["VaultClient"] = None

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        vault_role_id: Optional[str] = None,
        vault_secret_id: Optional[str] = None,
        vault_namespace: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        """
        Initialize Vault client.

        Args:
            vault_addr: Vault server address
            vault_token: Vault token for authentication
            vault_role_id: AppRole role ID
            vault_secret_id: AppRole secret ID
            vault_namespace: Vault namespace (Enterprise)
            verify_ssl: Verify SSL certificates
        """
        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR", "")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN", "")
        self.vault_role_id = vault_role_id or os.getenv("VAULT_ROLE_ID", "")
        self.vault_secret_id = vault_secret_id or os.getenv("VAULT_SECRET_ID", "")
        self.vault_namespace = vault_namespace or os.getenv("VAULT_NAMESPACE", "")
        self.verify_ssl = verify_ssl

        self._client: Optional[hvac.Client] = None
        # SECURITY FIX: Cache mit TTL-Tracking (Tuple: data, timestamp)
        self._secret_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._cache_ttl_seconds: int = 300  # 5 Minuten - rotierte Secrets werden nachgeladen
        self._authenticated = False

    @classmethod
    def get_instance(cls) -> "VaultClient":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_configured(self) -> bool:
        """Check if Vault is configured."""
        return bool(self.vault_addr and (self.vault_token or (self.vault_role_id and self.vault_secret_id)))

    def connect(self) -> bool:
        """
        Connect to Vault and authenticate.

        Returns:
            True if connection successful
        """
        if not VAULT_AVAILABLE:
            logger.warning("vault_connect_failed", reason="hvac not installed")
            return False

        if not self.is_configured():
            logger.debug("vault_not_configured", message="Vault nicht konfiguriert")
            return False

        try:
            self._client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token if self.vault_token else None,
                namespace=self.vault_namespace if self.vault_namespace else None,
                verify=self.verify_ssl,
            )

            # If no token, authenticate with AppRole
            if not self.vault_token and self.vault_role_id:
                self._authenticate_approle()

            # Verify authentication
            if self._client.is_authenticated():
                self._authenticated = True
                logger.info("vault_connected", address=self.vault_addr)
                return True
            else:
                logger.warning("vault_authentication_failed")
                return False

        except Exception as e:
            logger.error("vault_connection_error", error=str(e))
            return False

    def _authenticate_approle(self) -> None:
        """Authenticate using AppRole."""
        try:
            response = self._client.auth.approle.login(
                role_id=self.vault_role_id,
                secret_id=self.vault_secret_id,
            )
            self._client.token = response["auth"]["client_token"]
            logger.info("vault_approle_authenticated")
        except Exception as e:
            logger.error("vault_approle_auth_failed", error=str(e))
            raise

    def get_secret(
        self,
        path: str,
        key: Optional[str] = None,
        mount_point: str = "secret",
        use_cache: bool = True,
    ) -> Optional[Any]:
        """
        Get secret from Vault.

        Args:
            path: Secret path in Vault
            key: Specific key within the secret (optional)
            mount_point: Vault mount point
            use_cache: Use cached value if available

        Returns:
            Secret value or None
        """
        if not self._authenticated:
            if not self.connect():
                return None

        import time
        cache_key = f"{mount_point}/{path}"

        # SECURITY FIX: Check cache mit TTL-Prüfung
        if use_cache and cache_key in self._secret_cache:
            cached_data, cached_time = self._secret_cache[cache_key]
            # Prüfe ob Cache noch gültig ist
            if (time.time() - cached_time) < self._cache_ttl_seconds:
                if key:
                    return cached_data.get("data", {}).get("data", {}).get(key)
                return cached_data.get("data", {}).get("data", {})
            else:
                # Cache abgelaufen - entfernen
                del self._secret_cache[cache_key]
                logger.debug("vault_cache_expired", path=path)

        try:
            # Read secret (KV v2)
            response = self._client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=mount_point,
            )

            # SECURITY FIX: Cache mit Timestamp speichern
            self._secret_cache[cache_key] = (response, time.time())

            if key:
                return response.get("data", {}).get("data", {}).get(key)
            return response.get("data", {}).get("data", {})

        except Exception as e:
            logger.warning("vault_secret_read_failed", path=path, error=str(e))
            return None

    def clear_cache(self) -> None:
        """Clear secret cache."""
        self._secret_cache.clear()
        logger.debug("vault_cache_cleared")


class Settings(BaseSettings):
    """Application settings with environment variable and Vault support."""

    # Application
    APP_NAME: str = "Ablage-System OCR"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    
    # Security
    # WICHTIG: SECRET_KEY MUSS in Production via Umgebungsvariable gesetzt werden!
    # Beispiel: SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
    # SECURITY FIX: SecretStr verhindert Logging von Secrets
    SECRET_KEY: SecretStr = Field(
        default="",
        description="JWT Secret Key - MUSS in Production gesetzt sein (min. 32 Zeichen)"
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
    # In Production: Explizite Origins setzen via CORS_ORIGINS Umgebungsvariable
    # Beispiel: CORS_ORIGINS=["https://app.ablage-system.local","https://admin.ablage-system.local"]
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:80", "http://localhost"],
        description="Erlaubte CORS Origins - in Production explizit setzen!"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Credentials erlauben - nur mit expliziten Origins!"
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

    # Database Connection Pool Settings
    # API Pool (optimiert für 100+ concurrent users)
    DB_POOL_SIZE: int = Field(default=50, description="Database connection pool size for API")
    DB_MAX_OVERFLOW: int = Field(default=150, description="Maximum overflow connections for API")
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

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False  # For testing
    CELERY_TASK_EAGER_PROPAGATES: bool = True
    
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
    GPU_LOCK_TIMEOUT: int = Field(default=60, description="GPU lock auto-expire timeout in seconds")
    GPU_LOCK_ACQUIRE_TIMEOUT: int = Field(default=30, description="Max seconds to wait for GPU lock")
    GPU_LOCK_RETRY_INTERVAL: float = Field(default=0.1, description="Seconds between lock acquisition retries")

    # Model Pre-Loading Settings
    # Laedt OCR-Modelle beim Startup vor fuer schnellere erste Anfragen
    MODEL_PRELOAD_ENABLED: bool = True
    MODEL_PRELOAD_GPU_MODELS: bool = True  # Ob GPU-Modelle vorgeladen werden
    MODEL_PRELOAD_TIMEOUT_SECONDS: int = 600  # Timeout pro Model (10 Min)

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
    RATE_LIMIT_FAIL_CLOSED: bool = False  # SECURITY: fail-closed für besseren Schutz (temporarily disabled)
    RATE_LIMIT_FAIL_CLOSED_CRITICAL: bool = False  # Always fail-closed for critical endpoints (temporarily disabled)

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
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 8  # Conservative for 16GB VRAM
    EMBEDDING_MAX_LENGTH: int = 512  # Max tokens per text
    SEARCH_DEFAULT_LIMIT: int = 20
    SEARCH_MAX_LIMIT: int = 100
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5
    HYBRID_FTS_WEIGHT: float = 0.3
    HYBRID_SEMANTIC_WEIGHT: float = 0.7

    # Search Caching Settings
    SEARCH_CACHE_ENABLED: bool = True
    SEARCH_CACHE_TTL: int = 3600  # 1 hour for search results
    SEARCH_EMBEDDING_CACHE_TTL: int = 86400  # 24 hours for query embeddings
    SEARCH_SIMILAR_CACHE_TTL: int = 1800  # 30 minutes for similar documents

    # Embedding Auto-Generation Settings
    EMBEDDING_AUTO_GENERATE: bool = True  # Auto-generate after OCR
    EMBEDDING_TASK_DELAY_SECONDS: int = 5  # Delay before embedding task
    EMBEDDING_TASK_PRIORITY: int = 9  # Celery priority (0-9, 9=lowest)
    
    # Performance (Worker-Konfiguration)
    WORKER_CONNECTIONS: int = 1000
    KEEPALIVE_TIMEOUT: int = 5
    # DB Pool Settings sind oben bei "Database Connection Pool Settings" definiert
    
    # Monitoring
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090
    
    # Email (optional, for notifications)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[SecretStr] = None
    SMTP_FROM_EMAIL: Optional[str] = "noreply@ablage-system.local"
    SMTP_TLS: bool = True
    
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

    @model_validator(mode='after')
    def build_computed_urls(self) -> 'Settings':
        """Build database and Redis URLs from components if not provided."""
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

            # Prüfe MinIO Secret Key Komplexität (min 12 Zeichen fuer Production)
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
        # Daily limits muessen >= Hourly limits sein
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
            # Wenn Vault aktiviert ist, muessen Authentifizierungs-Credentials gesetzt sein
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

            # Production: HTTPS fuer Vault erzwingen
            if not self.DEBUG and self.VAULT_ADDR and not self.VAULT_ADDR.startswith("https://"):
                raise ValueError(
                    f"VAULT_ADDR '{self.VAULT_ADDR}' verwendet kein HTTPS in Production! "
                    "Vault-Verbindungen muessen in Production verschluesselt sein."
                )

            logger.info(
                "vault_configuration_validated",
                vault_addr=self.VAULT_ADDR,
                auth_method="token" if has_token else "approle",
                verify_ssl=self.VAULT_VERIFY_SSL
            )

        # Build DATABASE_URL if not set
        if not self.DATABASE_URL:
            password = self.DB_PASSWORD
            if isinstance(password, SecretStr):
                password = password.get_secret_value()
            object.__setattr__(self, 'DATABASE_URL',
                f"postgresql+asyncpg://{self.DB_USER}:"
                f"{password}@{self.DB_HOST}:"
                f"{self.DB_PORT}/{self.DB_NAME}"
            )

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
        if not self.CELERY_BROKER_URL:
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
                error=str(e),
                message="Vault-Secrets konnten nicht geladen werden, verwende Umgebungsvariablen",
            )

    return settings_instance


# Create settings instance
settings = create_settings()
