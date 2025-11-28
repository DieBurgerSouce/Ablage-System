"""Application configuration using Pydantic Settings."""

from typing import Optional, List, Dict, Any
from pathlib import Path
import secrets

from pydantic import Field, field_validator, SecretStr, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
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
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Database
    DB_USER: str = "ablage_admin"
    DB_PASSWORD: SecretStr = "changeme"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5433
    DB_NAME: str = "ablage_system"
    DATABASE_URL: Optional[str] = None
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[SecretStr] = None
    REDIS_URL: Optional[str] = None
    
    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False  # For testing
    CELERY_TASK_EAGER_PROPAGATES: bool = True
    
    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: SecretStr = "minioadmin123"
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
    GPU_MEMORY_FRACTION: float = 0.85  # Max 85% VRAM usage
    ENABLE_GPU: bool = True
    GPU_BATCH_SIZE: int = 32

    # Load Balancing Settings
    LOAD_BALANCING_ENABLED: bool = True
    QUEUE_LENGTH_THRESHOLD_HIGH: int = 100  # Switch to faster backend
    QUEUE_LENGTH_THRESHOLD_CRITICAL: int = 200  # Use CPU fallback
    QUEUE_CHECK_INTERVAL_SECONDS: int = 30  # How often to check queues
    LOAD_BALANCE_PREFER_GPU: bool = True  # Prefer GPU when queues similar

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_DOCUMENTS_PER_HOUR: int = 10
    DEFAULT_USER_DAILY_QUOTA: int = 100

    # Rate Limit Whitelist (comma-separated IPs)
    RATE_LIMIT_WHITELIST: List[str] = []

    # Rate Limit Tiers
    RATE_LIMIT_FREE_HOURLY: int = 10
    RATE_LIMIT_FREE_DAILY: int = 50
    RATE_LIMIT_PREMIUM_HOURLY: int = 100
    RATE_LIMIT_PREMIUM_DAILY: int = 1000
    RATE_LIMIT_ADMIN_HOURLY: int = 10000

    # Rate Limit Windows (in seconds)
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW: int = 900  # 15 minutes
    RATE_LIMIT_REGISTER_ATTEMPTS: int = 3
    RATE_LIMIT_REGISTER_WINDOW: int = 3600  # 1 hour

    # Rate Limit Storage
    RATE_LIMIT_STORAGE_URL: Optional[str] = None

    # German Language Settings
    GERMAN_VALIDATION_ENABLED: bool = True
    MINIMUM_GERMAN_VALIDATION_SCORE: float = 0.7
    DETECT_FRAKTUR: bool = True

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
    
    # Performance
    WORKER_CONNECTIONS: int = 1000
    KEEPALIVE_TIMEOUT: int = 5
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_PRE_PING: bool = True
    
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
    
    @model_validator(mode='after')
    def build_computed_urls(self) -> 'Settings':
        """Build database and Redis URLs from components if not provided."""
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


# Create settings instance
settings = Settings()
