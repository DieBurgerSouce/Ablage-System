# Service Integration Map

> **Enterprise Architecture Documentation**
>
> Vollständige Übersicht aller Services, ihrer Abhängigkeiten und Integrationen im Ablage-System.

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Core Service Layer](#2-core-service-layer)
3. [Domain-Specific Services](#3-domain-specific-services)
4. [External Integrations](#4-external-integrations)
5. [Celery Task System](#5-celery-task-system)
6. [API Router Dependencies](#6-api-router-dependencies)
7. [Service Dependency Graph](#7-service-dependency-graph)
8. [Error Handling & Resilience](#8-error-handling--resilience)
9. [Best Practices](#9-best-practices)

---

## 1. Executive Summary

### Systemübersicht

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Service Layer Statistics                         │
├─────────────────────────────────────────────────────────────────────────┤
│  Total Services:        150+     │  External Integrations: 1,113+      │
│  Core Services:         89+      │  Celery Tasks:          157         │
│  Service Categories:    19       │  API Routers:           58+         │
│  Inter-Service Deps:    237+     │  WebSocket Services:    1           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Kategorien

| Kategorie | Anzahl | Beschreibung |
|-----------|--------|--------------|
| Document Management | 6 | CRUD, GDPR, Batch, Export, Filter |
| OCR & Processing | 5 | Backends, Pipeline, Quality |
| Storage | 4 | MinIO, Thumbnails, Archive |
| Search & Semantic | 4 | FTS, Embeddings, Reranking |
| AI Intelligence | 6 | Anomaly, Duplicate, Categorization |
| Banking | 11 | Accounts, Transactions, Dunning |
| DATEV Integration | 7 | Export, Mapping, Tax Codes |
| RAG System | 10 | Chat, LLM, Vector Search |
| Validation | 6 | Queue, Samples, Analytics |
| Extraction | 4 | Line Items, Amounts, Payments |
| Personal/Privat | 11 | HR, Personal Finance |
| EInvoice | 3 | XRechnung, ZUGFeRD |
| ERP | 3 | Odoo, Sync Engine |
| Admin | 5 | Users, Audit, Rate Limits |
| Backup | 4 | Postgres, Redis, MinIO |
| ML/Advanced | 12 | Calibration, Training, Feedback |
| Utilities | 20+ | Auth, Notifications, Dashboard |
| Export/Reporting | 8+ | GDPR Export, Reports |
| German Language | 6 | Umlauts, Compounds, Fraktur |

---

## 2. Core Service Layer

### 2.1 Document Management Services

```
app/services/document_services/
├── crud_service.py        # Basis-CRUD-Operationen
├── filter_service.py      # Query-Building und Filterung
├── batch_service.py       # Bulk-Operationen (CANONICAL)
├── export_service.py      # Batch Document Export (CANONICAL)
└── gdpr_service.py        # Soft-Delete, Restore (CANONICAL)
```

#### DocumentService (Hauptorchestrator)

**Datei**: `app/services/document_service.py`

```python
class DocumentService:
    """Orchestriert alle Document-bezogenen Operationen."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.search_service = get_search_service()
        self.gdpr_service = DocumentGDPRService(db)
        self.batch_service = DocumentBatchService(db)
        self.export_service = DocumentExportService(db)
```

**Dependencies**:
- `SearchService` - Volltext- und semantische Suche
- `DocumentGDPRService` - GDPR-konforme Operationen
- `DocumentBatchService` - Bulk-Operationen
- `DocumentExportService` - Export-Funktionen
- `AsyncSession` - Datenbank-Session

**Connections**:
- PostgreSQL (Document, Tag, Folder Models)
- Redis (Cache Invalidation)

### 2.2 OCR & Processing Services

```
┌─────────────────────────────────────────────────────────────────┐
│                      OCR Service Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌────────────────┐    ┌─────────────────┐  │
│  │ OCRService  │───▶│ BackendManager │───▶│   GPU Manager   │  │
│  └─────────────┘    │   (Singleton)  │    └─────────────────┘  │
│         │           └────────────────┘              │           │
│         │                   │                       │           │
│         ▼                   ▼                       ▼           │
│  ┌─────────────┐    ┌─────────────────────────────────────┐    │
│  │  German     │    │          OCR Backends                │    │
│  │ Correction  │    │  ┌──────────┐ ┌────────┐ ┌───────┐  │    │
│  │   Agent     │    │  │ DeepSeek │ │GOT-OCR │ │ Surya │  │    │
│  └─────────────┘    │  │  (12GB)  │ │ (10GB) │ │(0-4GB)│  │    │
│                     │  └──────────┘ └────────┘ └───────┘  │    │
│                     └─────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### BackendManager (Singleton)

**Datei**: `app/services/backend_manager.py`

```python
class BackendManager:
    """Singleton: Verwaltet alle OCR-Backends und GPU-Ressourcen."""

    _instance: Optional["BackendManager"] = None

    def __init__(self):
        self.gpu_manager = GPUManager()
        self.health_cache = HealthCheckCache()
        self.quality_metrics = QualityMetrics()
        self.confidence_calibration = ConfidenceCalibration()
        self.drift_detector = DriftDetector()
```

**Dependencies**:
- `GPUManager` - VRAM-Management
- `HealthCheckCache` - Backend-Verfügbarkeit
- `QualityMetrics` - OCR-Qualitätsmessung
- `ConfidenceCalibration` - Konfidenz-Kalibrierung
- `DriftDetector` - ML Drift Detection

**Connections**:
- GPU/CUDA für alle Backends
- Prometheus Metrics

### 2.3 Storage Services

```
┌─────────────────────────────────────────────────────────────────┐
│                     Storage Architecture                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐                                             │
│  │ StorageService │──────────────────────┐                      │
│  └────────────────┘                      │                      │
│         │                                │                      │
│         ▼                                ▼                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     MinIO Server                         │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐  │   │
│  │  │  documents/   │  │  thumbnails/  │  │  exports/   │  │   │
│  │  │   (Primary)   │  │   (Previews)  │  │ (Generated) │  │   │
│  │  └───────────────┘  └───────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Features:                                                       │
│  - Server-Side Encryption                                        │
│  - Versioning für Recovery                                       │
│  - Presigned URLs für Direct Upload                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### StorageService

**Datei**: `app/services/storage_service.py`

**Buckets**:
| Bucket | Zweck | Größe (geschätzt) |
|--------|-------|-------------------|
| `documents/` | Original-Dokumente | 10-50 GB |
| `thumbnails/` | Preview-Bilder | 1-5 GB |
| `exports/` | Generierte Exports | 1-10 GB |

### 2.4 Search & Semantic Services

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hybrid Search Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                     ┌─────────────────┐                         │
│                     │  SearchService  │                         │
│                     └────────┬────────┘                         │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌────────────────┐       │
│  │  Full-Text  │    │  Semantic   │    │   Reranking    │       │
│  │   Search    │    │   Search    │    │   (BGE-RR)     │       │
│  │ (PostgreSQL │    │ (Embeddings)│    │                │       │
│  │   tsvector) │    │             │    │                │       │
│  └──────┬──────┘    └──────┬──────┘    └───────┬────────┘       │
│         │                  │                   │                 │
│         ▼                  ▼                   ▼                 │
│  ┌───────────────────────────────────────────────────────┐      │
│  │           Reciprocal Rank Fusion (RRF)                │      │
│  │         Adaptive Weights (Query-Length Based)          │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### SearchService

**Datei**: `app/services/search_service.py`

```python
class SearchService:
    """Hybrid Search: FTS + Semantic + Reranking."""

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.compound_splitter = GermanCompoundSplitter()
        self.reranker = RerankerService()
        self.redis = RedisStateManager()
```

**Dependencies**:
- `EmbeddingService` - multilingual-e5-large Embeddings
- `GermanCompoundSplitter` - Compound-Wort-Zerlegung
- `RerankerService` - BGE-Reranker
- `RedisStateManager` - Cache und State

**Search Flow**:
1. Query → German Compound Splitting
2. Parallel: FTS (PostgreSQL) + Semantic (pgvector/Qdrant)
3. Results → BGE Reranking
4. RRF Fusion → Ranked Results

---

## 3. Domain-Specific Services

### 3.1 AI Intelligence Services

**Pfad**: `app/services/ai/`

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Intelligence Module                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                  ┌───────────────────┐                          │
│                  │  AIDecisionService│                          │
│                  │     (Base)        │                          │
│                  └─────────┬─────────┘                          │
│                            │                                     │
│     ┌──────────────────────┼──────────────────────┐             │
│     ▼                      ▼                      ▼              │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐     │
│  │  Anomaly   │    │   Duplicate    │    │     Auto       │     │
│  │ Detection  │    │   Detection    │    │ Categorization │     │
│  └────────────┘    └────────────────┘    └────────────────┘     │
│                                                                  │
│                  ┌───────────────────┐                          │
│                  │ AILearningPipeline│                          │
│                  │ (Continuous Learn)│                          │
│                  └───────────────────┘                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| Service | Funktion | Input |
|---------|----------|-------|
| `AnomalyDetectionService` | Erkennt ungewöhnliche Beträge | Invoice amounts |
| `DuplicateDetectionService` | Findet Duplikate | Vendor, Amount, Date |
| `AutoCategorizationService` | Automatische Kategorisierung | Document text |
| `SmartMatchingService` | Dokument-Matching | Features |
| `AILearningPipeline` | Lernt aus Korrekturen | User feedback |

### 3.2 Banking Module

**Pfad**: `app/services/banking/`

```
┌─────────────────────────────────────────────────────────────────┐
│                      Banking Module                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Core Services:                                                  │
│  ├── AccountService                                              │
│  ├── TransactionService ◄─── Bank Parsers                       │
│  ├── ReconciliationService                                       │
│  └── PaymentService                                              │
│                                                                  │
│  Reporting:                                                      │
│  ├── CashFlowService                                             │
│  └── AgingReportService                                          │
│                                                                  │
│  Collections:                                                    │
│  ├── DunningService                                              │
│  ├── DunningStageService                                         │
│  └── MahnTaskService                                             │
│                                                                  │
│  Import:                                                         │
│  └── ImportService ◄─── Parsers:                                │
│      ├── MT940Parser                                             │
│      ├── CAMT053Parser                                           │
│      ├── CommerzbankCSVParser                                    │
│      ├── DeutscheBankCSVParser                                   │
│      ├── DKBCSVParser                                            │
│      ├── INGCSVParser                                            │
│      ├── N26CSVParser                                            │
│      ├── SparkasseCSVParser                                      │
│      └── VolksbankCSVParser                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 DATEV Integration

**Pfad**: `app/services/datev/`

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATEV Export Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │ DATEVExportSvc  │ ◄── Orchestrator                           │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┴─────┐                                               │
│     ▼           ▼                                                │
│  ┌───────────┐  ┌───────────┐                                   │
│  │ Invoice   │  │ TaxCode   │                                   │
│  │  Mapper   │  │  Mapper   │                                   │
│  └─────┬─────┘  └─────┬─────┘                                   │
│        │              │                                          │
│        ▼              ▼                                          │
│  ┌────────────────────────────┐                                 │
│  │   BuchungsstapelWriter     │                                 │
│  │   (DATEV CSV Format)       │                                 │
│  └────────────────────────────┘                                 │
│                  │                                               │
│                  ▼                                               │
│  ┌────────────────────────────┐                                 │
│  │  SKR03/SKR04 Kontenrahmen  │                                 │
│  └────────────────────────────┘                                 │
│                                                                  │
│  Output: DATEV-konforme CSV für Steuerberater                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 RAG System

**Pfad**: `app/services/rag/`

```
┌─────────────────────────────────────────────────────────────────┐
│                     RAG Architecture                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐         ┌──────────────┐                       │
│  │ ChatService │────────▶│  LLMService  │                       │
│  └──────┬──────┘         └──────────────┘                       │
│         │                        │                               │
│         ▼                        ▼                               │
│  ┌─────────────┐         ┌──────────────┐                       │
│  │SearchService│         │    Ollama    │ (lokal)               │
│  │   (RAG)     │         │ Claude API   │ (optional)            │
│  └──────┬──────┘         └──────────────┘                       │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Vector Storage                          │    │
│  │  ┌──────────────────┐    ┌───────────────────┐          │    │
│  │  │    Qdrant        │◄──►│    pgvector       │          │    │
│  │  │  (A/B Testing)   │    │   (Fallback)      │          │    │
│  │  │  10% → 100%      │    │                   │          │    │
│  │  └──────────────────┘    └───────────────────┘          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Supporting Services:                                            │
│  ├── ChunkingService      # Dokument-Segmentierung              │
│  ├── VectorSyncService    # Embedding-Synchronisation           │
│  ├── CustomerCardService  # Kundenprofil-Erstellung             │
│  ├── ExcelGenerator       # Report-Export                       │
│  └── WordGenerator        # Dokument-Export                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**A/B Testing Status** (Januar 2026):
- Phase 1: 10% Traffic → Qdrant
- 674 Vektoren indexiert
- Migration: 10% → 25% → 50% → 75% → 100%

---

## 4. External Integrations

### 4.1 Datenbank-Verbindungen

```
┌─────────────────────────────────────────────────────────────────┐
│                   Database Connections                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     PostgreSQL 16                         │   │
│  │  ├── Primary Data Store (1000+ Models)                   │   │
│  │  ├── SQLAlchemy 2.0 (Async Mode)                         │   │
│  │  ├── pgvector Extension (Embeddings)                     │   │
│  │  ├── Full-Text Search (German Stemmer)                   │   │
│  │  ├── Row-Level Security (RLS)                            │   │
│  │  └── Connection Pool: 20-50 Connections                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                       Redis 7.x                           │   │
│  │  ├── Cache Layer (Search, Embeddings, API)               │   │
│  │  ├── Job Queue (Celery Broker)                           │   │
│  │  ├── Session Storage (JWT Tokens)                        │   │
│  │  ├── Rate Limiting (API Key Buckets)                     │   │
│  │  ├── Pub/Sub (Real-Time Events)                          │   │
│  │  └── Max Memory: 2 GB                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Qdrant (Vector DB)                     │   │
│  │  ├── A/B Testing: 10% → 100% Traffic                     │   │
│  │  ├── 674 Vektoren indexiert                              │   │
│  │  └── Fallback: pgvector                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 AI/ML Services

| Service | Modell | VRAM | Zweck |
|---------|--------|------|-------|
| DeepSeek-Janus-Pro | 1.0 | 12 GB | Multimodal OCR |
| GOT-OCR | 2.0 (600M) | 10 GB | Transformer OCR |
| Surya | v1.1 | 0-4 GB | Layout-aware OCR |
| Docling | v1.0 | - | Document Understanding |
| multilingual-e5-large | - | 8 GB | Embeddings |
| BGE-Reranker | - | 2-4 GB | Reranking |
| Ollama | Various | - | Local LLM |

### 4.3 External APIs

| API | Zweck | Fallback |
|-----|-------|----------|
| Anthropic Claude | RAG LLM (optional) | Ollama lokal |
| Hugging Face | Model Downloads | Local Cache |
| SMTP | Email Notifications | Queue |
| Bank APIs | Transaction Feeds | Manual Import |

---

## 5. Celery Task System

### 5.1 Task-Übersicht

**157 Tasks in 26 Dateien**

```
app/workers/tasks/
├── ocr_tasks.py               # ~15 Tasks
├── document_intelligence_tasks.py  # ~12 Tasks
├── backup_tasks.py            # ~8 Tasks
├── training_tasks.py          # ~10 Tasks
├── banking_tasks.py           # ~8 Tasks
├── export_tasks.py            # ~8 Tasks
├── embedding_tasks.py         # ~6 Tasks
├── rag_tasks.py               # ~8 Tasks
├── notification_tasks.py      # ~5 Tasks
├── cleanup_tasks.py           # ~8 Tasks
├── monitoring_tasks.py        # ~8 Tasks
├── gdpr_tasks.py              # ~6 Tasks
├── import_tasks.py            # ~8 Tasks
├── erp_sync_tasks.py          # ~8 Tasks
├── workflow_tasks.py          # ~8 Tasks
└── [10+ weitere]              # ~40 Tasks
```

### 5.2 Task-Kategorien

| Kategorie | Beispiele | Service Dependencies |
|-----------|-----------|---------------------|
| OCR | `process_document`, `batch_ocr` | OCRService, GPUManager |
| Intelligence | `extract_entities`, `categorize` | AIDecisionService |
| Backup | `full_backup`, `sync_remote` | BackupService |
| Training | `update_weights`, `run_benchmarks` | OCRTrainingService |
| Banking | `import_transactions`, `reconcile` | BankingService |

### 5.3 Celery Beat Schedule

| Task | Zeitplan | Priority |
|------|----------|----------|
| `generate_daily_stats` | Täglich 01:00 | Low |
| `process_feedback_queue` | Stündlich | Medium |
| `update_learned_weights` | Täglich 02:00 | Low |
| `run_scheduled_benchmarks` | Sonntag 03:00 | Low |
| `full_backup` | Täglich 02:30 | High |
| `cleanup_old_tokens` | Täglich 04:00 | Low |
| `vector_sync` | Alle 5 Minuten | Medium |

---

## 6. API Router Dependencies

### 6.1 Router-Service Mapping

```
/api/v1/
├── documents.py
│   └── DocumentService, SearchService, StorageService, OCRService
│
├── ocr.py
│   └── OCRService, BulkOCRProcessingService, BenchmarkRunnerService
│
├── search.py
│   └── SearchService, EmbeddingService, RerankerService
│
├── training.py
│   └── OCRTrainingService, BenchmarkRunnerService, ValidationSampleService
│
├── banking.py
│   └── AccountService, TransactionService, ReconciliationService
│
├── datev.py
│   └── DATEVExportService, InvoiceMapper
│
├── gdpr.py
│   └── GDPRService, DocumentGDPRService, DataExportService
│
├── backup.py
│   └── BackupService, BackupMetricsService, BackupValidator
│
├── rag/
│   ├── chat.py      → ChatService, LLMService, SearchService
│   ├── search.py    → SearchService, VectorSyncService
│   └── chat_ws.py   → ChatService, ChatWebSocketManager
│
├── admin/
│   ├── users.py     → UserAdminService, PermissionService
│   ├── audit.py     → AuditService
│   ├── system.py    → SystemStatusService, GPUMetricsService
│   └── jobs.py      → JobAdminService, BatchJobService
│
└── health.py
    └── SystemStatusService, GPUMetricsService
```

---

## 7. Service Dependency Graph

### 7.1 Deepest Dependency Chain (OCR Processing)

```
FastAPI Route
  │
  └──▶ OCRService
        │
        └──▶ BackendManager (Singleton)
              │
              ├──▶ GPUManager
              ├──▶ HealthCheckCache
              ├──▶ QualityMetrics
              ├──▶ ConfidenceCalibration
              └──▶ DriftDetector
              │
              └──▶ DeepSeekOCRAgent | GOT-OCRAgent | Surya+Docling
                    │
                    └──▶ GPU (CUDA Kernels)
        │
        └──▶ GermanCorrectionAgent
              │
              └──▶ LanguageTool
        │
        └──▶ StorageService (MinIO)
        │
        └──▶ PostgreSQL (Document Model)
        │
        └──▶ SearchService (async)
              │
              ├──▶ EmbeddingService
              ├──▶ RerankerService
              └──▶ RedisStateManager
```

### 7.2 Search Pipeline

```
SearchService.hybrid_search()
  │
  ├──▶ GermanCompoundSplitter
  │      └── expand_umlaut_variants()
  │
  ├──▶ PostgreSQL.tsvector (FTS)
  │      └── German Stemmer
  │
  ├──▶ EmbeddingService
  │      ├── multilingual-e5-large
  │      └── Redis Cache
  │
  ├──▶ pgvector.cosine_distance() / Qdrant
  │
  ├──▶ RerankerService
  │      └── BGE-Reranker
  │
  └──▶ Reciprocal Rank Fusion (RRF)
         └── Adaptive Weights
```

---

## 8. Error Handling & Resilience

### 8.1 Circuit Breakers

```python
from app.services.circuit_breaker import CircuitBreaker

class WebhookCircuitBreaker:
    """
    States: CLOSED → OPEN → HALF_OPEN

    CLOSED:    Normal operation
    OPEN:      5+ failures → Block all requests (60s)
    HALF_OPEN: After recovery_timeout → Allow test request
    """

    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
```

### 8.2 Fallback-Ketten

| Service | Primary | Fallback 1 | Fallback 2 | Fallback 3 |
|---------|---------|------------|------------|------------|
| OCR | DeepSeek | GOT-OCR | Surya GPU | CPU |
| Search | Hybrid | FTS only | Cache | Empty |
| Storage | MinIO | Local FS | - | - |
| LLM | Ollama | Claude API | Cached | - |

### 8.3 Error Tracking

```python
# Strukturiertes Logging mit structlog
logger.error(
    "service_failure",
    service="ocr",
    error_type="gpu_oom",
    document_id=doc_id,
    vram_usage_gb=current_vram
)
```

**Regeln**:
- Kein PII in Logs
- Deutsche Fehlermeldungen an User
- Sentry/Custom für Aggregation

---

## 9. Best Practices

### 9.1 Service Instantiation

```python
# ✅ Singleton für stateless Services
def get_search_service() -> SearchService:
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service

# ✅ Per-Request für DB-abhängige Services
async def get_document_service(
    db: AsyncSession = Depends(get_db)
) -> DocumentService:
    return DocumentService(db)

# ✅ Lazy Loading mit ContextVar
def _get_search_service():
    service = _search_service_ctx.get()
    if service is None:
        from app.services.search_service import get_search_service
        service = get_search_service()
        _search_service_ctx.set(service)
    return service
```

### 9.2 Dependency Injection

```python
# FastAPI Dependency Injection
from fastapi import Depends

@router.post("/documents/")
async def create_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service)
) -> DocumentResponse:
    return await document_service.create(file, current_user)
```

### 9.3 Transaktions-Management

```python
# Atomic Database Operations
async with db.begin():
    document = await document_service.create(data)
    await search_service.index(document)
    await cache.invalidate(f"doc:{document.id}")
# Auto-commit on success, rollback on exception
```

### 9.4 Cache Invalidation

```python
@invalidate_on_document_change
async def update_document(doc_id: str, data: dict):
    """Decorator invalidates related cache keys."""
    ...

# Redis Key Patterns:
# - doc:{id}
# - search:{query_hash}
# - embed:{doc_id}
# TTL: 3600s default
```

---

## Anhang: Service Registry

### A. Alle Services nach Modul

```
app/services/
├── Core (22)
│   ├── document_service.py
│   ├── document_services/
│   │   ├── crud_service.py
│   │   ├── filter_service.py
│   │   ├── batch_service.py
│   │   ├── export_service.py
│   │   └── gdpr_service.py
│   ├── ocr_service.py
│   ├── backend_manager.py
│   ├── storage_service.py
│   ├── search_service.py
│   ├── embedding_service.py
│   └── ...
│
├── AI (6)
│   ├── anomaly_detection_service.py
│   ├── duplicate_detection_service.py
│   ├── auto_categorization_service.py
│   └── ...
│
├── Banking (11)
│   ├── core/
│   ├── reporting/
│   ├── collections/
│   └── import/
│
├── DATEV (7)
├── RAG (10)
├── Validation (6)
├── Extraction (4)
├── Personal (3)
├── Privat (8)
├── EInvoice (3)
├── ERP (3)
├── Admin (5)
├── Backup (4)
├── ML (12)
├── German Language (6)
└── Utilities (20+)

Total: 150+ Services
```

---

**Letzte Aktualisierung**: Januar 2026
**Version**: 1.0
**Maintainer**: Ablage-System Team
