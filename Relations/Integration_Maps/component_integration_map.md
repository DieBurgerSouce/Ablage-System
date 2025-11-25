# Component Integration Map - Ablage-System
**Version:** 1.0
**Status:** Living Document
**Letzte Aktualisierung:** 2025-11-23
**Zweck:** Master Reference für System-Integration

**Tags:** #architecture #integration #relations #system_design #architect #developer #devops #high #relations

---

## Überblick

Dieses Dokument bildet die **komplette Integration aller Systemkomponenten** ab. Es zeigt wie 50 Python-Module, 3 OCR-Backends, 10 Agents, 5 Services, und 6 Infrastructure-Komponenten zusammenarbeiten.

### Verwendung

**Zielgruppen:**
- **Architects:** System-Design-Entscheidungen verstehen
- **Developers:** Integration-Points für neue Features finden
- **DevOps:** Deployment-Topologie und Abhängigkeiten
- **QA:** Test-Szenarien und Integration-Tests planen

**Navigations-Hinweis:**
- 📊 Diagramme für visuelle Übersicht
- 📝 Textuelle Beschreibungen für Details
- 🔗 Links zu verwandter Dokumentation

---

## System-Architektur (High-Level)

### Gesamt-Übersicht

```mermaid
graph TB
    subgraph "Client Layer"
        UI[Web Frontend<br/>Vue.js/React]
        API_CLIENT[API Client<br/>HTTPx/Fetch]
    end

    subgraph "API Layer"
        FASTAPI[FastAPI<br/>app/main.py]
        AUTH[Authentication<br/>JWT/OAuth]
        RATELIMIT[Rate Limiter<br/>100 req/min]
    end

    subgraph "Agent Layer"
        COORDINATOR[Agent Coordinator<br/>Task Distribution]
        OCR_AGENT[OCR Agent]
        TEMPLATE_AGENT[Template Agent]
        BATCH_AGENT[Batch Agent]
        CLASSIFICATION_AGENT[Classification Agent]
    end

    subgraph "Service Layer"
        OCR_ORCHESTRATOR[OCR Orchestrator<br/>Backend Selection]
        DOCUMENT_SERVICE[Document Service]
        STORAGE_SERVICE[Storage Service]
        CACHE_SERVICE[Cache Service]
    end

    subgraph "OCR Backend Layer"
        DEEPSEEK[DeepSeek-Janus-Pro<br/>GPU, 12GB VRAM]
        GOT_OCR[GOT-OCR 2.0<br/>GPU, 10GB VRAM]
        SURYA[Surya+Docling<br/>CPU Fallback]
    end

    subgraph "Data Layer"
        POSTGRES[(PostgreSQL<br/>Documents, Users)]
        REDIS[(Redis<br/>Cache, Queue)]
        MINIO[(MinIO<br/>Object Storage)]
    end

    subgraph "Infrastructure Layer"
        GPU[NVIDIA RTX 4080<br/>16GB VRAM]
        CELERY[Celery Workers<br/>Async Tasks]
        PROMETHEUS[Prometheus<br/>Metrics]
        GRAFANA[Grafana<br/>Dashboards]
    end

    UI --> API_CLIENT
    API_CLIENT --> FASTAPI
    FASTAPI --> AUTH
    FASTAPI --> RATELIMIT
    FASTAPI --> COORDINATOR

    COORDINATOR --> OCR_AGENT
    COORDINATOR --> TEMPLATE_AGENT
    COORDINATOR --> BATCH_AGENT
    COORDINATOR --> CLASSIFICATION_AGENT

    OCR_AGENT --> OCR_ORCHESTRATOR
    TEMPLATE_AGENT --> DOCUMENT_SERVICE
    BATCH_AGENT --> OCR_ORCHESTRATOR

    OCR_ORCHESTRATOR --> DEEPSEEK
    OCR_ORCHESTRATOR --> GOT_OCR
    OCR_ORCHESTRATOR --> SURYA

    DOCUMENT_SERVICE --> STORAGE_SERVICE
    DOCUMENT_SERVICE --> CACHE_SERVICE
    STORAGE_SERVICE --> MINIO
    CACHE_SERVICE --> REDIS

    OCR_AGENT --> POSTGRES
    DOCUMENT_SERVICE --> POSTGRES

    DEEPSEEK --> GPU
    GOT_OCR --> GPU

    CELERY --> REDIS
    CELERY --> OCR_AGENT
    CELERY --> BATCH_AGENT

    PROMETHEUS --> FASTAPI
    PROMETHEUS --> CELERY
    GRAFANA --> PROMETHEUS
```

### Komponenten-Übersicht

| Layer | Komponenten | Technologie | Kritikalität |
|-------|------------|-------------|--------------|
| **Client** | Web Frontend | Vue.js/React | 🟡 MEDIUM |
| **API** | FastAPI, Auth, Rate Limiter | Python 3.11, FastAPI 0.110+ | 🟠 HIGH |
| **Agent** | 10 Agents, Coordinator | Python, Custom Framework | 🟠 HIGH |
| **Service** | 5 Services | Python, Async | 🔴 CRITICAL |
| **OCR Backend** | DeepSeek, GOT-OCR, Surya | PyTorch, Transformers | 🔴 CRITICAL |
| **Data** | PostgreSQL, Redis, MinIO | SQL, NoSQL, S3 | 🔴 CRITICAL |
| **Infrastructure** | GPU, Celery, Monitoring | CUDA, Celery, Prometheus | 🔴 CRITICAL |

---

## Detaillierte Komponenten-Integration

### 1. API Layer Integration

#### 1.1 FastAPI Application (`app/main.py`)

**Rolle:** API Gateway, Request Routing, Middleware

**Dependencies:**
```python
# Inbound:
- HTTP Clients (Frontend, Mobile App, CLI)

# Outbound:
- Agent Coordinator (app/agents/coordinator.py)
- Document Service (app/services/document_service.py)
- Authentication Service (app/core/security.py)
- Database (PostgreSQL)
- Cache (Redis)

# Infrastructure:
- Prometheus (Metrics export)
- Structured Logging (structlog)
```

**Integration Points:**
```python
# app/main.py
from fastapi import FastAPI, Depends
from app.api.v1 import documents, ocr, templates, auth
from app.core.logging import setup_logging
from app.core.metrics import setup_metrics

app = FastAPI(
    title="Ablage-System API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middleware Stack
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(RateLimitMiddleware, ...)
app.add_middleware(MetricsMiddleware, ...)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(ocr.router, prefix="/api/v1/ocr", tags=["ocr"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["templates"])

# Startup/Shutdown Events
@app.on_event("startup")
async def startup():
    # Initialize connections
    await database.connect()
    await redis.connect()
    await minio.connect()

    # Validate GPU environment
    validate_gpu_environment()

    # Setup monitoring
    setup_metrics()
```

**Data Flow:**
```
1. HTTP Request → FastAPI
2. Middleware: CORS, Rate Limit, Auth
3. Route Handler (app/api/v1/documents.py)
4. Dependency Injection (DB, User, Services)
5. Business Logic (Services/Agents)
6. Response Serialization (Pydantic)
7. HTTP Response → Client
```

#### 1.2 Authentication (`app/core/security.py`)

**Rolle:** JWT Authentication, User Management

**Integration:**
```python
# Dependencies:
- PostgreSQL (User storage)
- Redis (Session cache, blacklist)
- PassLib (Password hashing)
- Python-Jose (JWT)

# Used By:
- All protected API endpoints (via Depends(get_current_user))
- Frontend (login, token refresh)
```

**Authentication Flow:**
```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Auth
    participant Redis
    participant Postgres

    Client->>FastAPI: POST /auth/login (username, password)
    FastAPI->>Auth: authenticate_user()
    Auth->>Postgres: SELECT user WHERE username=?
    Postgres-->>Auth: User record
    Auth->>Auth: verify_password(hash, input)
    Auth->>Auth: create_access_token(user_id)
    Auth->>Redis: SETEX session:{token}
    Auth-->>FastAPI: {access_token, refresh_token}
    FastAPI-->>Client: 200 OK + tokens

    Client->>FastAPI: GET /documents (Authorization: Bearer token)
    FastAPI->>Auth: get_current_user(token)
    Auth->>Redis: GET session:{token}
    Redis-->>Auth: Session valid
    Auth->>Postgres: SELECT user WHERE id=?
    Postgres-->>Auth: User record
    Auth-->>FastAPI: Current user
    FastAPI->>DocumentService: get_user_documents(user)
    DocumentService-->>FastAPI: Documents
    FastAPI-->>Client: 200 OK + documents
```

### 2. Agent Layer Integration

#### 2.1 Agent Coordinator (`app/agents/coordinator.py`)

**Rolle:** Multi-Agent Orchestration, Task Distribution

**Integration:**
```python
# Dependencies:
- All Specialized Agents (OCR, Template, Batch, Classification, Validation)
- AgentRegistry (app/agents/agent_registry.py)
- Task Queue (Celery + Redis)
- Database (Task state persistence)

# Used By:
- API endpoints (trigger document processing)
- Celery workers (async processing)
- Scheduled tasks (batch jobs)
```

**Koordinations-Workflow:**
```mermaid
graph LR
    A[Coordinator] --> B{Document Type?}
    B -->|Invoice| C[OCR Agent]
    B -->|Form| D[Template Agent]
    B -->|Batch| E[Batch Agent]

    C --> F[Classification Agent]
    D --> F
    E --> F

    F --> G[Validation Agent]
    G --> H[Storage Agent]

    H --> I[Database]
    H --> J[MinIO]
```

**Code-Beispiel:**
```python
# app/agents/coordinator.py
class AgentCoordinator:
    def __init__(self):
        self.registry = AgentRegistry()
        self.task_queue = CeleryQueue()

    async def process_document(self, document_id: str) -> Dict[str, Any]:
        """
        Koordiniere Multi-Agent Workflow für Dokument.

        Workflow:
        1. Classify → Bestimme Dokumenttyp
        2. OCR → Extrahiere Text
        3. Template → Extrahiere strukturierte Daten (wenn anwendbar)
        4. Validate → Validiere Ergebnisse
        5. Store → Speichere in DB + MinIO
        """

        # 1. Classification
        classifier = self.registry.get_agent('classification')
        doc_type = await classifier.process({'document_id': document_id})

        # 2. OCR Processing
        ocr_agent = self.registry.get_agent('ocr')
        ocr_result = await ocr_agent.process({
            'document_id': document_id,
            'document_type': doc_type['type']
        })

        # 3. Template Extraction (conditional)
        if doc_type['type'] in ['invoice', 'form']:
            template_agent = self.registry.get_agent('template')
            extracted_data = await template_agent.process({
                'document_id': document_id,
                'ocr_text': ocr_result['text'],
                'template_type': doc_type['type']
            })
        else:
            extracted_data = None

        # 4. Validation
        validator = self.registry.get_agent('validation')
        validation_result = await validator.process({
            'ocr_result': ocr_result,
            'extracted_data': extracted_data
        })

        # 5. Storage (automatisch via Hooks)
        # StorageHook wird bei OCR completion getriggert

        return {
            'document_id': document_id,
            'status': 'completed',
            'document_type': doc_type,
            'ocr_result': ocr_result,
            'extracted_data': extracted_data,
            'validation': validation_result
        }
```

#### 2.2 OCR Agent (`app/agents/ocr_agent.py`)

**Integration:**
```python
# Dependencies:
- OCR Orchestrator (app/services/ocr/orchestrator.py)
- OCR Backends (deepseek, got_ocr, surya)
- GPU Manager (app/gpu_manager.py)
- German Validator (app/german_validator.py)
- Skills: BackendSelectionSkill, PreprocessingSkill
- Hooks: LoggingHook, MetricsHook, CacheHook

# Data Flow:
1. Receive Task (document_id, options)
2. Load Document (from MinIO via DocumentService)
3. Select Backend (via OCR Orchestrator)
4. Preprocess Image (via PreprocessingSkill)
5. Run OCR (GPU-accelerated, memory-guarded)
6. Post-process Text (German validation, spell check)
7. Store Result (PostgreSQL + Redis cache)
8. Trigger Hooks (metrics, logging, notifications)
```

**GPU Resource Management:**
```python
# OCR Agent mit GPU-Integration
class OCRAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="ocr_agent")
        self.gpu_manager = GPUManager()
        self.orchestrator = OCROrchestrator()

    async def _do_process_task(self, task: Dict) -> Dict:
        document_id = task['document_id']

        # GPU-Lock (verhindere Multi-Process Konflikte)
        async with self.gpu_manager.lock():
            # Memory Guard (verhindere OOM)
            with gpu_memory_guard(threshold_gb=13.6):
                # Backend selection
                backend = await self.orchestrator.select_backend(document_id)

                # OCR Processing
                result = await self.orchestrator.process(
                    document_id=document_id,
                    backend=backend
                )

        return result
```

### 3. Service Layer Integration

#### 3.1 OCR Orchestrator (`app/services/ocr/orchestrator.py`)

**Integration Map:**
```
OCR Orchestrator
├── Input: Document, Processing options
├── Output: OCR Result (text, confidence, metadata)
│
├── Dependencies:
│   ├── OCR Backends
│   │   ├── DeepSeekOCR (app/ocr_backends/deepseek.py)
│   │   ├── GOTOcrOCR (app/ocr_backends/got_ocr.py)
│   │   └── SuryaOCR (app/ocr_backends/surya.py)
│   │
│   ├── Services
│   │   ├── DocumentService (load image from MinIO)
│   │   └── CacheService (cache results)
│   │
│   ├── Utilities
│   │   ├── GPUManager (resource allocation)
│   │   ├── GermanValidator (umlaut validation)
│   │   └── ImagePreprocessor (image enhancement)
│   │
│   └── Skills
│       └── BackendSelectionSkill (intelligent routing)
│
└── Called By:
    ├── OCR Agent (primary user)
    ├── Batch Processing Agent
    └── API endpoints (direct OCR requests)
```

**Backend Selection Logic:**
```python
class OCROrchestrator:
    def select_backend(self, document: Document) -> str:
        """
        Decision Matrix:

        ┌─────────────────┬──────────┬───────────┬─────────┐
        │ Condition       │ DeepSeek │ GOT-OCR   │ Surya   │
        ├─────────────────┼──────────┼───────────┼─────────┤
        │ GPU available   │ ✅       │ ✅        │ Optional│
        │ Complex layout  │ ✅       │ ❌        │ ✅      │
        │ Fraktur script  │ ✅       │ ❌        │ ❌      │
        │ High umlaut     │ ✅       │ ⚠️        │ ❌      │
        │ Speed priority  │ ❌       │ ✅        │ ❌      │
        │ CPU-only        │ ❌       │ ❌        │ ✅      │
        └─────────────────┴──────────┴───────────┴─────────┘
        """

        # GPU check
        if not torch.cuda.is_available():
            return 'surya'  # CPU fallback

        # Document complexity
        if document.has_complex_layout:
            return 'deepseek'  # Best for complex layouts

        # Fraktur detection
        if document.contains_fraktur:
            return 'deepseek'  # Only backend with Fraktur support

        # German text with high umlaut density
        if document.language == 'de' and document.umlaut_density > 0.05:
            return 'deepseek'  # Best umlaut accuracy

        # Default: GOT-OCR (fast, good accuracy)
        return 'got_ocr'
```

#### 3.2 Document Service (`app/services/document_service.py`)

**Integration:**
```python
# Dependencies:
- DocumentRepository (app/db/repositories.py)
- StorageService (app/services/storage_service.py)
- CacheService (app/services/cache_service.py)
- PostgreSQL (metadata storage)
- MinIO (file storage)
- Redis (caching)

# Provides To:
- API endpoints (document CRUD)
- Agents (document loading)
- Workers (async processing)
```

**Data Flow:**
```mermaid
sequenceDiagram
    participant API
    participant DocService
    participant Storage
    participant Cache
    participant DB
    participant MinIO

    API->>DocService: upload_document(file, metadata)

    DocService->>Storage: store_file(file)
    Storage->>MinIO: PUT /documents/{uuid}.pdf
    MinIO-->>Storage: Object URL

    DocService->>DB: INSERT INTO documents
    DB-->>DocService: Document ID

    DocService->>Cache: SETEX doc:{id}
    Cache-->>DocService: OK

    DocService-->>API: Document{id, url, metadata}
```

#### 3.3 Storage Service (`app/services/storage_service.py`)

**Integration:**
```python
# MinIO S3-Compatible Storage

# Configuration:
- Endpoint: minio:9000
- Access Key: (from env)
- Secret Key: (from env)
- Bucket: documents

# Dependencies:
- MinIO (infrastructure)
- boto3 / aioboto3 (S3 client)

# Provides To:
- DocumentService (file upload/download)
- OCR Agents (image loading)
- API (file serving)
```

**Operations:**
```python
class StorageService:
    async def upload(self, file_data: bytes, filename: str) -> str:
        """Upload file to MinIO, return object URL."""

    async def download(self, object_key: str) -> bytes:
        """Download file from MinIO."""

    async def delete(self, object_key: str) -> bool:
        """Delete file from MinIO."""

    async def get_presigned_url(self, object_key: str, expiry: int = 3600) -> str:
        """Generate temporary download URL."""
```

### 4. OCR Backend Integration

#### 4.1 Backend Comparison Matrix

| Feature | DeepSeek | GOT-OCR | Surya |
|---------|----------|---------|-------|
| **GPU Required** | ✅ Yes (12GB) | ✅ Yes (10GB) | ❌ No (CPU) |
| **Speed** | 2-3 pages/s | 5-7 pages/s | 1-2 pages/s |
| **Umlaut Accuracy** | 99-100% | 95-98% | 85-90% |
| **Complex Layouts** | ✅ Excellent | ⚠️ Limited | ✅ Excellent |
| **Fraktur Support** | ✅ Yes | ❌ No | ❌ No |
| **Best For** | German docs, Complex | Fast processing | CPU-only, Layout |

#### 4.2 DeepSeek Integration

**Dependencies:**
```python
# Model:
- deepseek/Janus-Pro-1.0 (Hugging Face)
- transformers 4.35+
- torch 2.1+ (CUDA 12.x)

# Hardware:
- NVIDIA RTX 4080 (16GB VRAM)
- CUDA 12.1+
- cuDNN 8.9+

# Integration Points:
- GPU Manager (VRAM allocation)
- German Validator (post-processing)
- Image Preprocessor (input preparation)
```

**Processing Pipeline:**
```python
# app/ocr_backends/deepseek.py
class DeepSeekOCR:
    def __init__(self):
        self.model = self._load_model()  # 12GB VRAM
        self.processor = self._load_processor()
        self.gpu_manager = GPUManager()

    @torch.no_grad()
    def process(self, image_path: str) -> Dict:
        """
        Pipeline:
        1. Load & Preprocess Image
        2. Allocate GPU Memory
        3. Model Inference (Multimodal)
        4. Decode Output
        5. German Validation
        6. Return Result + Metrics
        """

        # 1. Preprocessing
        image = Image.open(image_path)
        inputs = self.processor(image, return_tensors='pt').to('cuda')

        # 2. GPU Memory Check
        with gpu_memory_guard(threshold_gb=13.6):
            # 3. Inference
            outputs = self.model.generate(**inputs, max_length=2048)

            # 4. Decode
            text = self.processor.decode(outputs[0], skip_special_tokens=True)

        # 5. German Validation
        validator = GermanValidator()
        validated_text = validator.validate_and_correct(text)

        # 6. Metrics
        return {
            'text': validated_text,
            'raw_text': text,
            'backend': 'deepseek',
            'processing_time': ...,
            'umlaut_accuracy': ...,
            'gpu_memory_used': ...
        }
```

### 5. Data Layer Integration

#### 5.1 PostgreSQL Schema

**Database: `ablage_db`**

```sql
-- Users & Authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',  -- 'user', 'admin', 'operator'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100),
    language VARCHAR(10) DEFAULT 'de',
    storage_path TEXT NOT NULL,  -- MinIO object key
    document_type VARCHAR(100),  -- 'invoice', 'form', 'letter', etc.
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- OCR Results
CREATE TABLE ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    backend VARCHAR(50) NOT NULL,  -- 'deepseek', 'got_ocr', 'surya'
    extracted_text TEXT NOT NULL,
    raw_text TEXT,
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    processing_time FLOAT,  -- seconds
    umlaut_accuracy FLOAT,
    gpu_memory_used BIGINT,  -- bytes
    quality_flags JSONB DEFAULT '[]',
    needs_manual_review BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Templates
CREATE TABLE templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    template_type VARCHAR(100),  -- 'invoice', 'form', etc.
    pattern JSONB NOT NULL,  -- Field extraction rules
    created_by UUID REFERENCES users(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Agent Tasks (State tracking)
CREATE TABLE agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL,
    task_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for Performance
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_ocr_results_document_id ON ocr_results(document_id);
CREATE INDEX idx_ocr_results_backend ON ocr_results(backend);
CREATE INDEX idx_ocr_results_created_at ON ocr_results(created_at DESC);
CREATE INDEX idx_agent_tasks_status ON agent_tasks(status);
CREATE INDEX idx_agent_tasks_agent_id ON agent_tasks(agent_id);
```

#### 5.2 Redis Caching Strategy

**Key Patterns:**
```
# Document Metadata Cache
doc:{document_id} → DocumentModel (JSON)
TTL: 1 hour

# OCR Result Cache
ocr:{document_id}:{backend} → OCRResult (JSON)
TTL: 24 hours

# User Session
session:{token} → UserSession (JSON)
TTL: 15 minutes (access token)

# Rate Limiting
ratelimit:{user_id}:{endpoint} → Counter
TTL: 1 minute

# Celery Task Queue
celery:task:{task_id} → Task State
celery:queue:default → Task Queue (List)
celery:queue:ocr_tasks → OCR Task Queue (List)
```

**Integration:**
```python
# app/services/cache_service.py
class CacheService:
    def __init__(self):
        self.redis = Redis(host='redis', port=6379, decode_responses=True)

    async def cache_document(self, document: Document, ttl: int = 3600):
        """Cache document metadata."""
        key = f"doc:{document.id}"
        value = document.json()
        await self.redis.setex(key, ttl, value)

    async def get_cached_document(self, document_id: str) -> Optional[Document]:
        """Retrieve cached document."""
        key = f"doc:{document_id}"
        value = await self.redis.get(key)
        return Document.parse_raw(value) if value else None

    async def cache_ocr_result(self, result: OCRResult, ttl: int = 86400):
        """Cache OCR result (24h TTL)."""
        key = f"ocr:{result.document_id}:{result.backend}"
        await self.redis.setex(key, ttl, result.json())
```

### 6. Infrastructure Integration

#### 6.1 Deployment Architecture

**Production Topology:**
```
┌─────────────────────────────────────────────────────────────┐
│ INTERNET                                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │ Nginx Reverse Proxy│
              │ SSL Termination    │
              │ Load Balancer      │
              └─────────┬──────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
    │ FastAPI │   │ FastAPI │   │ FastAPI │
    │ Instance│   │ Instance│   │ Instance│
    │ :8000   │   │ :8001   │   │ :8002   │
    └────┬────┘   └────┬────┘   └────┬────┘
         │              │              │
         └──────────────┼──────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
    │ Celery  │   │ Celery  │   │ Celery  │
    │ Worker  │   │ Worker  │   │ Worker  │
    │ GPU     │   │ (no GPU)│   │ (no GPU)│
    └────┬────┘   └────┬────┘   └────┬────┘
         │              │              │
         └──────────────┼──────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────▼─────┐   ┌───▼────┐   ┌────▼────┐
    │PostgreSQL│   │ Redis  │   │  MinIO  │
    │   :5432  │   │ :6379  │   │  :9000  │
    └──────────┘   └────────┘   └─────────┘
```

#### 6.2 Docker Compose Integration

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Frontend
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://backend:8000
    depends_on:
      - backend

  # Backend API
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/ablage_db
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
      - USE_GPU=true
    depends_on:
      - postgres
      - redis
      - minio
    volumes:
      - ./app:/app/app
      - ./models:/app/models  # Model cache
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  # Celery Worker (GPU-enabled)
  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/ablage_db
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
      - NVIDIA_VISIBLE_DEVICES=0
      - CUDA_VISIBLE_DEVICES=0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    depends_on:
      - redis
      - postgres
      - minio
    command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=1 --pool=solo

  # PostgreSQL
  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=ablage_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # MinIO (S3-compatible storage)
  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"  # API
      - "9001:9001"  # Console
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password123
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  # Grafana
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  postgres_data:
  redis_data:
  minio_data:
  prometheus_data:
  grafana_data:
```

### 7. Monitoring & Observability Integration

#### 7.1 Prometheus Metrics

**Exported Metrics:**
```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# API Metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# OCR Metrics
ocr_processing_duration = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing time',
    ['backend', 'document_type']
)

ocr_accuracy = Gauge(
    'ocr_accuracy_percent',
    'OCR accuracy',
    ['backend', 'metric_type']  # metric_type: 'character', 'word', 'umlaut'
)

# GPU Metrics
gpu_memory_usage = Gauge('gpu_memory_usage_bytes', 'GPU memory usage')
gpu_utilization = Gauge('gpu_utilization_percent', 'GPU utilization')
gpu_temperature = Gauge('gpu_temperature_celsius', 'GPU temperature')

# Agent Metrics
agent_tasks_total = Counter(
    'agent_tasks_total',
    'Total agent tasks',
    ['agent_id', 'status']  # status: 'completed', 'failed'
)

agent_task_duration = Histogram(
    'agent_task_duration_seconds',
    'Agent task duration',
    ['agent_id']
)

# Database Metrics
db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation', 'table']
)

db_connection_pool = Gauge(
    'db_connection_pool_size',
    'Database connection pool size',
    ['state']  # state: 'active', 'idle'
)
```

#### 7.2 Grafana Dashboards

**Dashboard 1: System Overview**
```json
{
  "dashboard": {
    "title": "Ablage-System Overview",
    "panels": [
      {
        "title": "API Request Rate",
        "targets": [{"expr": "rate(api_requests_total[5m])"}]
      },
      {
        "title": "OCR Processing Time (p95)",
        "targets": [{"expr": "histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket[5m]))"}]
      },
      {
        "title": "GPU Memory Usage",
        "targets": [{"expr": "gpu_memory_usage_bytes / gpu_memory_total_bytes * 100"}]
      },
      {
        "title": "Agent Task Success Rate",
        "targets": [{"expr": "rate(agent_tasks_total{status='completed'}[5m]) / rate(agent_tasks_total[5m]) * 100"}]
      }
    ]
  }
}
```

**Dashboard 2: OCR Quality**
```json
{
  "dashboard": {
    "title": "OCR Quality Monitoring",
    "panels": [
      {
        "title": "Umlaut Accuracy by Backend",
        "targets": [{"expr": "ocr_accuracy{metric_type='umlaut'}"}]
      },
      {
        "title": "Processing Time Comparison",
        "targets": [
          {"expr": "histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket{backend='deepseek'}[5m]))"},
          {"expr": "histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket{backend='got_ocr'}[5m]))"},
          {"expr": "histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket{backend='surya'}[5m]))"}
        ]
      }
    ]
  }
}
```

---

## Data Flow Scenarios

### Scenario 1: Document Upload & OCR Processing

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant DocService
    participant MinIO
    participant DB
    participant Coordinator
    participant OCRAgent
    participant DeepSeek
    participant GPU

    User->>Frontend: Upload invoice.pdf
    Frontend->>API: POST /api/v1/documents/upload
    API->>DocService: upload_document(file, metadata)

    DocService->>MinIO: Store file
    MinIO-->>DocService: Object URL

    DocService->>DB: INSERT INTO documents
    DB-->>DocService: Document ID

    DocService-->>API: Document{id, status: 'uploaded'}
    API-->>Frontend: 202 Accepted + document_id

    API->>Coordinator: process_document(document_id)
    Coordinator->>OCRAgent: process_task{document_id}

    OCRAgent->>DocService: load_document(document_id)
    DocService->>MinIO: GET file
    MinIO-->>DocService: File bytes
    DocService-->>OCRAgent: Image data

    OCRAgent->>DeepSeek: process(image)
    DeepSeek->>GPU: Allocate VRAM (12GB)
    DeepSeek->>GPU: Model inference
    GPU-->>DeepSeek: Output tokens
    DeepSeek-->>OCRAgent: OCR Result

    OCRAgent->>DB: INSERT INTO ocr_results
    DB-->>OCRAgent: Result ID

    OCRAgent-->>Coordinator: Task completed
    Coordinator-->>API: Processing complete

    API->>Frontend: WebSocket: {status: 'completed', result_id}
    Frontend-->>User: Show extracted text
```

### Scenario 2: Batch Processing

```mermaid
graph TD
    A[User uploads 100 PDFs] --> B[Batch Processing Agent]

    B --> C{GPU Available?}
    C -->|Yes| D[Group into batches of 16]
    C -->|No| E[Queue for later]

    D --> F[OCR Agent: Process Batch 1]
    D --> G[OCR Agent: Process Batch 2]
    D --> H[OCR Agent: Process Batch 6]

    F --> I[DeepSeek: Batch inference]
    G --> I
    H --> I

    I --> J[Results stored in DB]
    J --> K[Cache results in Redis]
    K --> L[Notify user: Batch complete]
```

### Scenario 3: Template Extraction (Invoice)

```mermaid
sequenceDiagram
    participant OCRAgent
    participant TemplateAgent
    participant TemplateSkill
    participant DB

    OCRAgent->>TemplateAgent: {text, document_type: 'invoice'}
    TemplateAgent->>DB: Load invoice template
    DB-->>TemplateAgent: Template{patterns}

    TemplateAgent->>TemplateSkill: extract_fields(text, patterns)
    TemplateSkill->>TemplateSkill: Apply regex patterns
    TemplateSkill->>TemplateSkill: Validate extracted data

    TemplateSkill-->>TemplateAgent: {
        invoice_number: "12345",
        date: "2025-11-23",
        amount: 1234.56,
        vendor: "Müller GmbH"
    }

    TemplateAgent->>DB: Store extracted data
    TemplateAgent-->>OCRAgent: Extraction complete
```

---

## Integration Testing Strategy

### Critical Integration Points to Test

1. **API → Agent → OCR Pipeline**
   ```python
   async def test_end_to_end_ocr():
       # Upload document via API
       response = await client.post("/api/v1/documents/upload", files={"file": pdf_file})
       document_id = response.json()["id"]

       # Wait for OCR processing
       await wait_for_completion(document_id, timeout=30)

       # Verify OCR result
       result = await client.get(f"/api/v1/ocr/{document_id}/results")
       assert result.json()["text"] contains "expected text"
       assert result.json()["umlaut_accuracy"] >= 95.0
   ```

2. **Database Transactions & Consistency**
   ```python
   async def test_transaction_rollback_on_error():
       # Start transaction
       # Upload document → DB insert
       # Trigger OCR → Fails
       # Verify: Document NOT in DB (rollback worked)
   ```

3. **GPU Resource Contention**
   ```python
   async def test_concurrent_gpu_access():
       # Start 3 OCR tasks simultaneously
       # Verify: Only 1 uses GPU at a time (lock working)
       # Verify: Others wait in queue
       # Verify: All complete successfully
   ```

4. **Cache Invalidation**
   ```python
   async def test_cache_invalidation():
       # Process document → Result cached
       # Reprocess document with different backend
       # Verify: Old cache invalidated
       # Verify: New result cached
   ```

---

## Dependency Graph

```
PostgreSQL ──┐
             ├──→ DocumentService ──→ API Endpoints
Redis ───────┤                          ↓
             │                    Agent Coordinator
MinIO ───────┘                          ↓
                                   ┌────┴────┐
                                   │ Agents  │
                                   ├─────────┤
                                   │  OCR    │←── OCR Orchestrator ←── Backends (DeepSeek, GOT-OCR, Surya)
                                   │Template │                              ↓
                                   │  Batch  │                         GPU Manager
                                   └─────────┘                              ↓
                                                                        RTX 4080
```

---

## Verwandte Dokumentation

- **[agent_implementation_roadmap.md](../../Static_Knowledge/Implementation_Guides/agent_implementation_roadmap.md)** - Implementation Plan
- **[code_index.md](../../Meta_Layer/Indexes/code_index.md)** - File Dependencies
- **[agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md)** - Deployment Details
- **[gpu_troubleshooting_guide.md](../../Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md)** - GPU Integration Issues

---

## Changelog

| Version | Datum | Änderungen | Autor |
|---------|-------|-----------|-------|
| 1.0 | 2025-11-23 | Initial integration map: Complete system architecture | Development Team |

---

**Maintainer:** Architecture Team
**Review:** Quarterly oder bei Major-Änderungen
**Nächstes Review:** 2026-02-23
