# Dependency Injection Patterns - Ablage-System

> **Stand**: Januar 2026
> **Status**: Enterprise-Ready
> **Pattern-Count**: 8+ verschiedene DI-Ansätze

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [FastAPI Depends()](#fastapi-depends)
3. [Service-Injection (Lazy Loading)](#service-injection-lazy-loading)
4. [Repository Pattern](#repository-pattern)
5. [Factory Pattern](#factory-pattern)
6. [Singleton Pattern](#singleton-pattern)
7. [Async Context Manager](#async-context-manager)
8. [Configuration Injection](#configuration-injection)
9. [Best Practices](#best-practices)

---

## Übersicht

Das Ablage-System nutzt ein **mehrschichtiges Dependency Injection System** mit komplementären Patterns:

| Pattern | Schicht | Zweck | Testbarkeit |
|---------|---------|-------|-------------|
| FastAPI `Depends()` | HTTP Layer | Request-scoped Injection | Hoch |
| Service-Injection | Service Layer | Lazy Loading | Hoch |
| Repository Pattern | Data Layer | Datenzugriff-Abstraktion | Hoch |
| Factory Pattern | Service Layer | Instanz-Erstellung | Hoch |
| Singleton Pattern | Infrastructure | Globale Manager | Mittel |
| Context Manager | Task Layer | Celery/Standalone Kontexte | Hoch |
| Config Injection | Core | Zentrale Konfiguration | Hoch |

### Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Request                          │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Depends() Layer                                    │
│  ├── get_db() → AsyncSession                               │
│  ├── get_current_user() → User                             │
│  ├── check_rate_limit() → User                             │
│  └── get_current_superuser() → User                        │
├─────────────────────────────────────────────────────────────┤
│  Service Layer                                               │
│  ├── Factory Functions: get_*_service()                    │
│  ├── Lazy Properties: _service → Service()                 │
│  └── Singleton Instances: GPUManager, Config               │
├─────────────────────────────────────────────────────────────┤
│  Repository Layer                                            │
│  ├── BaseRepository<T> (Generic CRUD)                      │
│  └── DocumentRepository, UserRepository, etc.              │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure Layer                                        │
│  ├── DatabaseManager (Singleton)                           │
│  ├── RedisStateManager (Singleton)                         │
│  └── StorageService (Singleton)                            │
└─────────────────────────────────────────────────────────────┘
```

---

## FastAPI Depends()

### HTTP Request Injection

**Datei**: `app/api/dependencies.py`

#### Datenbank-Dependency

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Engine mit Connection Pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,       # Default: 50
    max_overflow=settings.DB_MAX_OVERFLOW,  # Default: 150
    pool_pre_ping=settings.DB_POOL_PRE_PING,
)

# Async Session Maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> Generator[AsyncSession, None, None]:
    """Dependency für DB-Session mit Auto-Commit/Rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

#### Authentication Chain

```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(scheme_name="JWT", auto_error=True)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Token validieren und User laden."""
    token = credentials.credentials
    payload = await decode_token(token)

    user = await UserService.get_user_by_id(db, UUID(payload["sub"]))
    if not user:
        raise HTTPException(401, "Benutzer nicht gefunden")
    if not user.is_active:
        raise HTTPException(403, "Benutzer deaktiviert")

    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Prüfe ob User aktiv ist."""
    if not current_user.is_active:
        raise HTTPException(403, "Inaktiver Benutzer")
    return current_user

async def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Nur Administratoren."""
    if not current_user.is_superuser:
        raise HTTPException(403, "Nur Administratoren haben Zugriff")
    return current_user
```

#### Rate Limiting Dependency

```python
async def check_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> User:
    """OCR-Rate-Limits prüfen."""
    storage = await get_redis_storage()

    # User-Tier Limits
    limits = {
        "admin": 10000,
        "premium": 100,
        "free": 10
    }

    key = f"ocr_rate_limit:{current_user.id}:hourly"
    count = await storage.increment(key, 3600)

    if count > limits.get(current_user.tier, 10):
        raise HTTPException(
            status_code=429,
            detail="Rate limit überschritten",
            headers={"Retry-After": "3600"}
        )

    return current_user
```

#### Dependency Stacking

```python
@router.post("/documents/process")
async def process_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),           # 1. DB Session
    user: User = Depends(get_current_user),        # 2. Authentication
    _: User = Depends(check_rate_limit)            # 3. Rate Limiting
):
    """3-Level Dependency Chain."""
    # Alle Dependencies werden nacheinander aufgelöst
    service = DocumentService(db)
    return await service.process(file, user.id)
```

---

## Service-Injection (Lazy Loading)

### Property-basiertes Lazy Loading

**Datei**: `app/services/document_services/ablage_service.py`

```python
class AblageService(DocumentServiceBase):
    """Kategorie-basierte Dokumentenverwaltung."""

    def __init__(self):
        """Initialisiere OHNE externe Dependencies."""
        self._storage_service = None
        self._embedding_service = None

    @property
    def storage_service(self) -> StorageService:
        """Lazy-Loading für Storage-Service."""
        if self._storage_service is None:
            self._storage_service = get_storage_service()
        return self._storage_service

    @property
    def embedding_service(self) -> EmbeddingService:
        """Lazy-Loading für Embedding-Service."""
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    async def bulk_download_zip(self, doc_ids: List[UUID]) -> bytes:
        """Lazy-Service wird erst hier aufgerufen."""
        storage = self.storage_service  # Nur bei Bedarf geladen
        files = []
        for doc_id in doc_ids:
            files.append(await storage.download(doc_id))
        return self._create_zip(files)
```

### Vorteile

1. **Performance**: Services werden nur bei Bedarf instantiiert
2. **Memory**: Keine ungenutzten Service-Instanzen
3. **Testbarkeit**: Properties können gemockt werden
4. **Flexibilität**: Unterschiedliche Services pro Kontext möglich

---

## Repository Pattern

### Generische Basis-Klasse

**Datei**: `app/db/repositories/base.py`

```python
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

ModelType = TypeVar("ModelType", bound=DeclarativeBase)

class BaseRepository(Generic[ModelType], ABC):
    """Generisches Basis-Repository mit CRUD-Operationen."""

    def __init__(self, db: AsyncSession, model: Type[ModelType]):
        self.db = db
        self.model = model

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """Einzelnes Objekt laden."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelType]:
        """Alle Objekte mit Pagination."""
        query = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, obj_data: Dict[str, Any]) -> ModelType:
        """Neues Objekt erstellen."""
        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        id: UUID,
        obj_data: Dict[str, Any]
    ) -> Optional[ModelType]:
        """Objekt aktualisieren."""
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return None
        for field, value in obj_data.items():
            setattr(db_obj, field, value)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, id: UUID) -> bool:
        """Objekt löschen."""
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return False
        await self.db.delete(db_obj)
        await self.db.commit()
        return True

    async def bulk_create(
        self,
        objects_data: List[Dict[str, Any]]
    ) -> List[ModelType]:
        """Mehrere Objekte erstellen."""
        db_objs = [self.model(**data) for data in objects_data]
        self.db.add_all(db_objs)
        await self.db.commit()
        return db_objs
```

### Spezialisierte Repositories

**Datei**: `app/db/repositories/document_repository.py`

```python
class DocumentRepository(BaseRepository[Document]):
    """Dokument-spezifische Datenbankoperationen."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Document)

    async def get_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ProcessingStatus] = None,
        include_deleted: bool = False
    ) -> List[Document]:
        """Alle Dokumente eines Users."""
        query = select(Document).where(
            Document.owner_id == owner_id
        ).options(
            selectinload(Document.tags)  # N+1 Query Fix
        )

        if not include_deleted:
            query = query.where(Document.deleted_at.is_(None))

        if status:
            query = query.where(Document.status == status)

        query = query.order_by(Document.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_checksum(self, checksum: str) -> Optional[Document]:
        """Duplikatserkennung via Checksum."""
        result = await self.db.execute(
            select(Document).where(Document.checksum == checksum)
        )
        return result.scalar_one_or_none()

    async def full_text_search(
        self,
        query: str,
        owner_id: UUID,
        limit: int = 20
    ) -> List[Document]:
        """PostgreSQL Full-Text Search."""
        from sqlalchemy import func

        stmt = select(Document).where(
            Document.owner_id == owner_id,
            func.to_tsvector('german', Document.extracted_text).match(query)
        ).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
```

### Repository im Service verwenden

```python
class DocumentService:
    def __init__(self, db: AsyncSession):
        self.repository = DocumentRepository(db)

    async def get_user_documents(
        self,
        user_id: UUID,
        page: int = 1,
        per_page: int = 20
    ) -> List[Document]:
        skip = (page - 1) * per_page
        return await self.repository.get_by_owner(
            user_id,
            skip=skip,
            limit=per_page
        )
```

---

## Factory Pattern

### Service Factory Functions

**Konvention**: `get_*_service()` Funktionen für Service-Instanziierung

```python
# app/services/storage_service.py
def get_storage_service() -> StorageService:
    """Factory-Funktion für StorageService."""
    return StorageService()

# app/services/confidence_service.py
def get_confidence_service() -> ConfidenceService:
    """Factory-Funktion für ConfidenceService."""
    return ConfidenceService()

# app/services/api_key_service.py
def get_api_key_service() -> APIKeyService:
    """Factory-Funktion für APIKeyService."""
    return APIKeyService()

# app/services/embedding_service.py
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()

def get_jina_embedding_service() -> JinaEmbeddingService:
    return JinaEmbeddingService()

# app/services/vector/reranker_service.py
def get_reranker_service() -> RerankerService:
    return RerankerService()

# app/services/gpu_metrics_service.py
def get_gpu_metrics_service() -> GPUMetricsService:
    return GPUMetricsService()
```

**Vorteile**:
- Type-safe: IDE kennt Return-Type
- Testbar: Factory kann in Tests überschrieben werden
- Flexibel: Konfiguration kann in Factory eingebaut werden
- Konsistent: Einheitliches Muster im gesamten Codebase

### Factory mit Konfiguration

```python
def get_ocr_service(
    backend: str = "auto",
    use_gpu: bool = True
) -> OCRService:
    """Factory mit Konfigurationsoptionen."""
    config = OCRConfig(
        backend=backend,
        use_gpu=use_gpu,
        batch_size=get_optimal_batch_size(backend)
    )
    return OCRService(config)
```

---

## Singleton Pattern

### Database Manager Singleton

**Datei**: `app/db/database.py`

```python
class DatabaseManager:
    """Singleton database manager mit Connection Pooling."""

    _instance: Optional['DatabaseManager'] = None
    _engine = None
    _session_maker = None

    def __new__(cls):
        """Stelle sicher, dass nur eine Instanz existiert."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Lazy Initialization."""
        if self._engine is None:
            self.config = DatabaseConfig()
            self._initialize_engine()

    def _initialize_engine(self):
        """Initialisiere Engine mit Pooling."""
        self._engine = create_async_engine(
            self.config.DATABASE_URL,
            pool_size=self.config.POOL_SIZE,
            max_overflow=self.config.MAX_OVERFLOW,
            pool_timeout=self.config.POOL_TIMEOUT,
            pool_recycle=self.config.POOL_RECYCLE,
            pool_pre_ping=True,
        )

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self):
        if self._engine is None:
            self._initialize_engine()
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get session with automatic cleanup."""
        session = self.session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def health_check(self) -> dict:
        """Check database connectivity and pool status."""
        pool = self._engine.pool
        return {
            "status": "healthy",
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }

def get_database_manager() -> DatabaseManager:
    """Get singleton instance."""
    return DatabaseManager()
```

### GPU Manager Singleton

**Datei**: `app/gpu_manager.py`

```python
_gpu_manager: Optional[GPUManager] = None
_memory_guard: Optional[GPUMemoryGuard] = None
_batch_processor: Optional[AdaptiveBatchProcessor] = None

def get_gpu_manager() -> GPUManager:
    """Get singleton GPU manager instance."""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager()
    return _gpu_manager

def get_memory_guard() -> GPUMemoryGuard:
    """Get singleton memory guard instance."""
    global _memory_guard
    if _memory_guard is None:
        _memory_guard = GPUMemoryGuard()
    return _memory_guard

def get_batch_processor() -> AdaptiveBatchProcessor:
    """Get singleton batch processor instance."""
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = AdaptiveBatchProcessor()
    return _batch_processor
```

---

## Async Context Manager

### Session Context für Celery Tasks

**Datei**: `app/db/session.py`

```python
@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager für Celery Tasks.

    WICHTIG: Engine wird INNERHALB des async context erstellt,
    um Event-Loop-Fehler in separaten Prozessen zu vermeiden.
    """
    # Engine inside async context
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )

    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    session = async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await engine.dispose()
```

### Verwendung in Celery Task

```python
@celery_app.task
async def process_document_task(doc_id: UUID):
    """Celery Task mit Dependency Injection."""
    async with get_async_session_context() as session:
        # Session ist hier verfügbar
        repository = DocumentRepository(session)
        doc = await repository.get_by_id(doc_id)

        # OCR verarbeiten
        ocr_service = get_ocr_service()
        result = await ocr_service.process(doc)

        # Status aktualisieren
        doc.status = ProcessingStatus.COMPLETED
        doc.extracted_text = result.text
        await session.commit()
```

### GPU Memory Guard Context

```python
from contextlib import contextmanager

@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6):
    """Context Manager für GPU Memory Protection."""
    initial_memory = torch.cuda.memory_allocated()
    try:
        yield
    finally:
        peak_memory_gb = torch.cuda.max_memory_allocated() / (1024 ** 3)
        if peak_memory_gb > threshold_gb:
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

# Verwendung
with gpu_memory_guard(required_gb=10.0):
    result = model.process(data)
```

---

## Configuration Injection

### Zentrale Settings

**Datei**: `app/core/config.py`

```python
from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr, model_validator

class Settings(BaseSettings):
    """Pydantic Settings mit Vault-Integration."""

    # API
    APP_NAME: str = "Ablage-System OCR"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: SecretStr = Field(..., min_length=32)
    ENCRYPTION_KEY: Optional[SecretStr] = None

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 50
    DB_MAX_OVERFLOW: int = 150

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # GPU
    GPU_MEMORY_FRACTION: float = 0.85
    GPU_BATCH_SIZE: int = 32

    # Vault (Optional)
    VAULT_ENABLED: bool = False
    VAULT_URL: Optional[str] = None
    VAULT_TOKEN: Optional[SecretStr] = None

    @model_validator(mode='after')
    def build_computed_urls(self) -> 'Settings':
        """Validiere Production Settings."""
        # SECRET_KEY Validierung
        if not self.DEBUG:
            key = self.SECRET_KEY.get_secret_value()
            if len(key) < 32:
                raise ValueError("SECRET_KEY muss mindestens 32 Zeichen haben")

        return self

    def load_secrets_from_vault(self) -> bool:
        """Load secrets von HashiCorp Vault."""
        if not self.VAULT_ENABLED:
            return False

        import hvac
        client = hvac.Client(
            url=self.VAULT_URL,
            token=self.VAULT_TOKEN.get_secret_value()
        )

        secrets = client.secrets.kv.v2.read_secret_version(
            path="ablage-system"
        )

        # Override settings
        self.SECRET_KEY = SecretStr(secrets["data"]["data"]["secret_key"])
        return True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Globale Singleton-Instanz
def create_settings() -> Settings:
    settings_instance = Settings()
    if settings_instance.VAULT_ENABLED:
        settings_instance.load_secrets_from_vault()
    return settings_instance

settings = create_settings()
```

### Settings verwenden

```python
from app.core.config import settings

# Überall im Code verfügbar
db_url = settings.DATABASE_URL
secret = settings.SECRET_KEY.get_secret_value()
batch_size = settings.GPU_BATCH_SIZE
```

---

## Best Practices

### 1. Dependency Stacking

```python
# Gute Praxis: Klare Dependency Chain
@router.post("/documents/process")
async def process_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _rate_limit = Depends(check_rate_limit),
):
    """Dependencies werden in Reihenfolge aufgelöst."""
    pass
```

### 2. Lazy Loading für Performance

```python
# Gute Praxis: Service nur bei Bedarf laden
class MyService:
    @property
    def expensive_service(self):
        if self._expensive_service is None:
            self._expensive_service = ExpensiveService()
        return self._expensive_service
```

### 3. Transaction Management

```python
# Gute Praxis: Auto-Commit/Rollback
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### 4. Type Safety

```python
# Gute Praxis: Return-Types in Factory Functions
def get_service() -> ConfidenceService:
    return ConfidenceService()

# IDE und mypy kennen den Type
service: ConfidenceService = get_service()
```

### 5. Testbarkeit

```python
# Gute Praxis: Dependencies in Tests überschreiben
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)
    return session

async def test_get_document(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = Document(...)

    repo = DocumentRepository(mock_db)
    result = await repo.get_by_id(UUID("..."))

    assert result is not None
```

---

## Referenzen

- **FastAPI Dependency Injection**: https://fastapi.tiangolo.com/tutorial/dependencies/
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Pydantic Settings**: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
