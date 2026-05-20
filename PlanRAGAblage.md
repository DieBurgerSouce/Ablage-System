RAG Ablage-System


# RAG/LLM Intelligence Layer - Technische Spezifikation

> **Version:** 1.0.0
> **Status:** Planning → Implementation Ready
> **Zielgruppe:** Claude Code / Opus für autonome Implementierung
> **Projekt:** Ablage-System (Enterprise Document Intelligence)
> **Erstellt:** 2025-12-03

---

## Executive Summary

Dieses Dokument spezifiziert die Erweiterung des Ablage-Systems um einen **RAG (Retrieval-Augmented Generation) Intelligence Layer**. Das Modul ermöglicht es Unternehmen, mit ihren gescannten Dokumenten zu "chatten" und automatisierte Reports zu generieren - vollständig on-premises und GDPR-konform.

### Kernfähigkeiten

| Fähigkeit | Beschreibung | Latenz-Ziel |
|-----------|--------------|-------------|
| **Semantic Search** | Natürlichsprachliche Dokumentensuche | < 500ms |
| **Real-Time Chat** | Telefon-Support, Quick Facts | < 15 sek |
| **Deep Analysis** | Komplexe Vertragsanalysen, Trends | < 60 sek |
| **Report Generation** | Excel, PDF, Word automatisch erstellen | Batch |
| **Customer Cards** | Pre-computed Kunden-Zusammenfassungen | < 1 sek |

---

## 1. Architektur-Übersicht

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ABLAGE-SYSTEM ARCHITECTURE                           │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        EXISTING SYSTEM                                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │ │
│  │  │   Frontend   │  │  API Gateway │  │ Orchestrator │  │    OCR     │ │ │
│  │  │   React 19   │  │   FastAPI    │  │   Routing    │  │  Backends  │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │ │
│  │                                                                         │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │ │
│  │  │  PostgreSQL  │  │    Redis     │  │    MinIO     │  │ Prometheus │ │ │
│  │  │   Primary    │  │    Queue     │  │   Storage    │  │  Grafana   │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    NEW: RAG INTELLIGENCE LAYER                          │ │
│  │                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │                      VECTOR STORAGE                              │   │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │ │
│  │  │  │  pgvector   │  │  Document   │  │     Embedding Index     │  │   │ │
│  │  │  │  Extension  │  │   Chunks    │  │   (IVFFlat / HNSW)      │  │   │ │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │                      MODEL SERVICES                              │   │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │ │
│  │  │  │  Embedding  │  │  Reranker   │  │      LLM Inference      │  │   │ │
│  │  │  │   Service   │  │   Service   │  │   (Ollama / llama.cpp)  │  │   │ │
│  │  │  │             │  │             │  │                         │  │   │ │
│  │  │  │ multilingual│  │ bge-reranker│  │  ┌─────────┐ ┌───────┐  │  │   │ │
│  │  │  │  -e5-large  │  │   -v2-m3    │  │  │Qwen3-8B │ │Qwen3- │  │  │   │ │
│  │  │  │             │  │             │  │  │Real-Time│ │  14B  │  │  │   │ │
│  │  │  └─────────────┘  └─────────────┘  │  └─────────┘ └───────┘  │  │   │ │
│  │  │                                     └─────────────────────────┘  │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │                    APPLICATION SERVICES                          │   │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │ │
│  │  │  │   Search    │  │    Chat     │  │    Report Generator     │  │   │ │
│  │  │  │   Engine    │  │   Service   │  │   (Excel/PDF/Word)      │  │   │ │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │ │
│  │  │                                                                  │   │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │ │
│  │  │  │  Customer   │  │    Model    │  │     Batch Processor     │  │   │ │
│  │  │  │   Cards     │  │   Router    │  │    (Nightly Jobs)       │  │   │ │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW PIPELINE                                │
│                                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Document │───▶│   OCR    │───▶│  Store   │───▶│  Chunk   │              │
│  │  Upload  │    │ Process  │    │ in PG    │    │  + Embed │              │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘              │
│                                                        │                    │
│                                                        ▼                    │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         RETRIEVAL PIPELINE                            │  │
│  │                                                                       │  │
│  │   User Query                                                          │  │
│  │       │                                                               │  │
│  │       ▼                                                               │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │  │
│  │  │  Embed   │───▶│  Vector  │───▶│ Rerank   │───▶│  Top K   │        │  │
│  │  │  Query   │    │  Search  │    │ Results  │    │  Chunks  │        │  │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │  │
│  │                                                        │              │  │
│  │                                                        ▼              │  │
│  │  ┌──────────────────────────────────────────────────────────────┐    │  │
│  │  │                    GENERATION PIPELINE                        │    │  │
│  │  │                                                               │    │  │
│  │  │  ┌──────────┐    ┌──────────┐    ┌──────────┐                │    │  │
│  │  │  │  Model   │───▶│   LLM    │───▶│ Response │                │    │  │
│  │  │  │  Router  │    │ Generate │    │ + Source │                │    │  │
│  │  │  └──────────┘    └──────────┘    └──────────┘                │    │  │
│  │  └──────────────────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Datenbank-Schema

### 2.1 PostgreSQL Extensions

```sql
-- Erforderliche Extensions
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector für Embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- Trigram für Fuzzy-Search
CREATE EXTENSION IF NOT EXISTS btree_gin;     -- GIN Index Support
```

### 2.2 Core Tables

```sql
-- ============================================================================
-- DOCUMENT CHUNKS TABLE
-- Speichert die chunked Dokumente mit Embeddings für RAG
-- ============================================================================
CREATE TABLE rag_document_chunks (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Referenz zum Original-Dokument (existierende Tabelle)
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    -- Chunk-Metadaten
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_tokens INTEGER NOT NULL,

    -- Positionierung im Dokument
    page_number INTEGER,
    section_type VARCHAR(50),  -- 'header', 'paragraph', 'table', 'list', 'footer'
    bounding_box JSONB,        -- {"x": 0, "y": 0, "width": 100, "height": 50}

    -- Embedding Vector (1024 Dimensionen für multilingual-e5-large)
    embedding vector(1024) NOT NULL,

    -- Embedding-Metadaten
    embedding_model VARCHAR(100) NOT NULL DEFAULT 'intfloat/multilingual-e5-large',
    embedding_created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_chunk_index CHECK (chunk_index >= 0),
    CONSTRAINT valid_chunk_tokens CHECK (chunk_tokens > 0 AND chunk_tokens <= 8192)
);

-- Unique constraint für Document + Chunk Index
CREATE UNIQUE INDEX idx_chunks_document_index
    ON rag_document_chunks(document_id, chunk_index);

-- Vector Index für Semantic Search (IVFFlat für große Datenmengen)
CREATE INDEX idx_chunks_embedding_ivfflat
    ON rag_document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);  -- Anpassen basierend auf Datenmenge

-- Alternative: HNSW Index (schneller, mehr RAM)
-- CREATE INDEX idx_chunks_embedding_hnsw
--     ON rag_document_chunks
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- GIN Index für Section Type Filtering
CREATE INDEX idx_chunks_section_type ON rag_document_chunks(section_type);

-- B-Tree Index für Page Number Range Queries
CREATE INDEX idx_chunks_page_number ON rag_document_chunks(page_number);

-- ============================================================================
-- CUSTOMER CARDS TABLE
-- Pre-computed Kunden-Zusammenfassungen für Real-Time Zugriff
-- ============================================================================
CREATE TABLE rag_customer_cards (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Kunden-Identifikation
    customer_id VARCHAR(100) NOT NULL UNIQUE,
    customer_name VARCHAR(255) NOT NULL,
    customer_type VARCHAR(50),  -- 'Stammkunde', 'Neukunde', 'Inaktiv'

    -- Pre-Computed Summaries (vom LLM generiert)
    summary_text TEXT NOT NULL,
    quick_facts JSONB NOT NULL DEFAULT '[]',

    -- Strukturierte Daten
    open_invoices JSONB DEFAULT '[]',
    active_contracts JSONB DEFAULT '[]',
    recent_orders JSONB DEFAULT '[]',

    -- Metriken
    total_revenue_ytd DECIMAL(15, 2),
    total_revenue_last_year DECIMAL(15, 2),
    average_order_value DECIMAL(15, 2),
    payment_behavior VARCHAR(50),  -- 'Pünktlich', 'Verzögert', 'Problematisch'

    -- Flags und Alerts
    flags JSONB DEFAULT '[]',  -- ["Zahlungsverzug", "Vertrag läuft aus"]
    priority_level INTEGER DEFAULT 0,  -- 0-10, höher = wichtiger

    -- Synchronisation
    last_full_sync_at TIMESTAMPTZ,
    last_incremental_sync_at TIMESTAMPTZ,
    sync_status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'syncing', 'completed', 'error'
    sync_error_message TEXT,

    -- Source Documents (für Nachvollziehbarkeit)
    source_document_ids UUID[] DEFAULT '{}',
    source_document_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Embedding für Card-Search
    card_embedding vector(1024)
);

-- Indices für Customer Cards
CREATE INDEX idx_customer_cards_name_trgm
    ON rag_customer_cards
    USING gin (customer_name gin_trgm_ops);

CREATE INDEX idx_customer_cards_type ON rag_customer_cards(customer_type);
CREATE INDEX idx_customer_cards_priority ON rag_customer_cards(priority_level DESC);
CREATE INDEX idx_customer_cards_sync_status ON rag_customer_cards(sync_status);

-- ============================================================================
-- CHAT SESSIONS TABLE
-- Speichert Chat-Konversationen für Context
-- ============================================================================
CREATE TABLE rag_chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User/Session Identifikation
    user_id UUID NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,

    -- Session Metadaten
    title VARCHAR(255),
    context_type VARCHAR(50),  -- 'general', 'customer', 'document', 'report'
    context_id VARCHAR(255),   -- z.B. customer_id oder document_id

    -- Session Status
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'archived', 'deleted'
    message_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ
);

CREATE INDEX idx_chat_sessions_user ON rag_chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_context ON rag_chat_sessions(context_type, context_id);

-- ============================================================================
-- CHAT MESSAGES TABLE
-- Einzelne Nachrichten in einer Session
-- ============================================================================
CREATE TABLE rag_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Referenz zur Session
    session_id UUID NOT NULL REFERENCES rag_chat_sessions(id) ON DELETE CASCADE,

    -- Message Content
    role VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,

    -- Für Assistant Messages: Quellen
    source_chunks UUID[] DEFAULT '{}',  -- Referenzen zu rag_document_chunks
    source_documents UUID[] DEFAULT '{}',
    confidence_score FLOAT,

    -- Model Information
    model_used VARCHAR(100),
    tokens_used INTEGER,
    generation_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session ON rag_chat_messages(session_id);
CREATE INDEX idx_chat_messages_created ON rag_chat_messages(created_at);

-- ============================================================================
-- LLM MODEL REGISTRY TABLE
-- Registrierte LLM Modelle und ihre Konfiguration
-- ============================================================================
CREATE TABLE rag_llm_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Model Identifikation
    model_name VARCHAR(100) NOT NULL UNIQUE,
    model_type VARCHAR(50) NOT NULL,  -- 'chat', 'embedding', 'reranker'
    provider VARCHAR(50) NOT NULL,    -- 'ollama', 'llama.cpp', 'huggingface-tei'

    -- Model Specs
    parameters_billions FLOAT,
    context_window INTEGER,
    quantization VARCHAR(20),  -- 'Q4_K_M', 'Q8_0', 'FP16', etc.

    -- Resource Requirements
    ram_required_gb FLOAT,
    vram_required_gb FLOAT,

    -- Performance Metrics
    avg_tokens_per_second FLOAT,
    avg_latency_ms INTEGER,

    -- Routing Configuration
    use_case VARCHAR(50),  -- 'realtime', 'batch', 'embedding', 'reranking'
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,

    -- Endpoint Configuration
    endpoint_url VARCHAR(255),
    api_key_env_var VARCHAR(100),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- BATCH JOBS TABLE
-- Tracking für Batch-Processing (Reports, Customer Card Updates)
-- ============================================================================
CREATE TABLE rag_batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job Identifikation
    job_type VARCHAR(50) NOT NULL,  -- 'customer_card_sync', 'report_generation', 'reembedding'
    job_name VARCHAR(255),

    -- Job Parameters
    parameters JSONB DEFAULT '{}',

    -- Status Tracking
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed', 'cancelled'
    progress_percent INTEGER DEFAULT 0,
    progress_message TEXT,

    -- Results
    result JSONB,
    output_file_path VARCHAR(500),

    -- Error Handling
    error_message TEXT,
    error_stack TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Timing
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_batch_jobs_status ON rag_batch_jobs(status);
CREATE INDEX idx_batch_jobs_type ON rag_batch_jobs(job_type);
CREATE INDEX idx_batch_jobs_scheduled ON rag_batch_jobs(scheduled_at);

-- ============================================================================
-- ANALYTICS / METRICS TABLE
-- Tracking von Nutzung und Performance
-- ============================================================================
CREATE TABLE rag_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Event Type
    event_type VARCHAR(50) NOT NULL,  -- 'search', 'chat', 'report', 'customer_card_view'

    -- Context
    user_id UUID,
    session_id UUID,

    -- Query/Request Details
    query_text TEXT,
    query_embedding vector(1024),

    -- Results
    results_count INTEGER,
    top_result_score FLOAT,

    -- Performance
    total_latency_ms INTEGER,
    embedding_latency_ms INTEGER,
    search_latency_ms INTEGER,
    rerank_latency_ms INTEGER,
    llm_latency_ms INTEGER,

    -- Model Info
    llm_model_used VARCHAR(100),
    tokens_input INTEGER,
    tokens_output INTEGER,

    -- User Feedback
    feedback_rating INTEGER,  -- 1-5
    feedback_text TEXT,

    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_event_type ON rag_analytics(event_type);
CREATE INDEX idx_analytics_created ON rag_analytics(created_at);
CREATE INDEX idx_analytics_user ON rag_analytics(user_id);

-- Partitionierung für Analytics (optional, bei großen Datenmengen)
-- CREATE TABLE rag_analytics_partitioned (...) PARTITION BY RANGE (created_at);
```

### 2.3 Database Functions

```sql
-- ============================================================================
-- SEMANTIC SEARCH FUNCTION
-- Hauptfunktion für RAG Retrieval
-- ============================================================================
CREATE OR REPLACE FUNCTION rag_semantic_search(
    query_embedding vector(1024),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INTEGER DEFAULT 20,
    filter_document_ids UUID[] DEFAULT NULL,
    filter_section_types VARCHAR(50)[] DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    chunk_text TEXT,
    page_number INTEGER,
    section_type VARCHAR(50),
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.chunk_text,
        c.page_number,
        c.section_type,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM rag_document_chunks c
    WHERE
        -- Similarity Threshold
        1 - (c.embedding <=> query_embedding) > match_threshold
        -- Optional Document Filter
        AND (filter_document_ids IS NULL OR c.document_id = ANY(filter_document_ids))
        -- Optional Section Type Filter
        AND (filter_section_types IS NULL OR c.section_type = ANY(filter_section_types))
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- HYBRID SEARCH FUNCTION
-- Kombiniert Semantic + Keyword Search
-- ============================================================================
CREATE OR REPLACE FUNCTION rag_hybrid_search(
    query_embedding vector(1024),
    query_text TEXT,
    semantic_weight FLOAT DEFAULT 0.7,
    keyword_weight FLOAT DEFAULT 0.3,
    match_count INTEGER DEFAULT 20
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    chunk_text TEXT,
    combined_score FLOAT,
    semantic_score FLOAT,
    keyword_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH semantic_results AS (
        SELECT
            c.id,
            c.document_id,
            c.chunk_text,
            1 - (c.embedding <=> query_embedding) AS score
        FROM rag_document_chunks c
        ORDER BY c.embedding <=> query_embedding
        LIMIT match_count * 2
    ),
    keyword_results AS (
        SELECT
            c.id,
            c.document_id,
            c.chunk_text,
            similarity(c.chunk_text, query_text) AS score
        FROM rag_document_chunks c
        WHERE c.chunk_text % query_text
        ORDER BY similarity(c.chunk_text, query_text) DESC
        LIMIT match_count * 2
    ),
    combined AS (
        SELECT
            COALESCE(s.id, k.id) AS id,
            COALESCE(s.document_id, k.document_id) AS document_id,
            COALESCE(s.chunk_text, k.chunk_text) AS chunk_text,
            COALESCE(s.score, 0) AS sem_score,
            COALESCE(k.score, 0) AS kw_score
        FROM semantic_results s
        FULL OUTER JOIN keyword_results k ON s.id = k.id
    )
    SELECT
        combined.id AS chunk_id,
        combined.document_id,
        combined.chunk_text,
        (combined.sem_score * semantic_weight + combined.kw_score * keyword_weight) AS combined_score,
        combined.sem_score AS semantic_score,
        combined.kw_score AS keyword_score
    FROM combined
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- CUSTOMER CARD UPDATE TRIGGER
-- Automatisches Update von updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_customer_cards_updated_at
    BEFORE UPDATE ON rag_customer_cards
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_document_chunks_updated_at
    BEFORE UPDATE ON rag_document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

## 3. Model Configuration

### 3.1 Model Portfolio

```yaml
# config/rag_models.yaml
# Konfiguration für alle RAG-relevanten Modelle

models:
  # =========================================================================
  # EMBEDDING MODEL
  # Immer aktiv, generiert Vektoren für alle Dokumente und Queries
  # =========================================================================
  embedding:
    name: "multilingual-e5-large"
    provider: "huggingface-tei"  # Text Embeddings Inference
    model_id: "intfloat/multilingual-e5-large"

    specs:
      dimensions: 1024
      max_tokens: 512
      languages: 100+

    resources:
      ram_gb: 2.5
      cpu_threads: 4

    performance:
      throughput_docs_per_sec: 50
      latency_ms: 20

    deployment:
      replicas: 1
      port: 8081
      health_endpoint: "/health"

  # =========================================================================
  # RERANKER MODEL
  # Verbessert Suchergebnisse durch Cross-Encoding
  # =========================================================================
  reranker:
    name: "bge-reranker-v2-m3"
    provider: "huggingface-tei"
    model_id: "BAAI/bge-reranker-v2-m3"

    specs:
      max_tokens: 512
      languages: 100+

    resources:
      ram_gb: 1.5
      cpu_threads: 2

    performance:
      throughput_pairs_per_sec: 100
      latency_ms: 10

    deployment:
      replicas: 1
      port: 8082
      health_endpoint: "/health"

  # =========================================================================
  # REAL-TIME LLM
  # Für Telefon-Support, Quick Chat, einfache Fragen
  # =========================================================================
  llm_realtime:
    name: "qwen3-8b"
    provider: "ollama"
    model_id: "qwen3:8b-q4_K_M"

    specs:
      parameters_b: 8
      context_window: 128000
      quantization: "Q4_K_M"
      thinking_mode: true
      languages: 119

    resources:
      ram_gb: 8
      cpu_threads: 8

    performance:
      tokens_per_sec_cpu: 15-20
      typical_response_time_sec: 10-15

    use_cases:
      - "telefon_support"
      - "quick_facts"
      - "simple_questions"
      - "document_summary_short"

    deployment:
      replicas: 1
      port: 11434
      model_keep_alive: "24h"

  # =========================================================================
  # DEEP ANALYSIS LLM
  # Für komplexe Analysen, Reports, Batch-Processing
  # =========================================================================
  llm_analysis:
    name: "qwen3-14b"
    provider: "ollama"
    model_id: "qwen3:14b-q4_K_M"

    specs:
      parameters_b: 14
      context_window: 128000
      quantization: "Q4_K_M"
      thinking_mode: true
      languages: 119

    resources:
      ram_gb: 12
      cpu_threads: 12

    performance:
      tokens_per_sec_cpu: 8-12
      typical_response_time_sec: 30-60

    use_cases:
      - "contract_analysis"
      - "trend_detection"
      - "report_generation"
      - "customer_card_generation"
      - "complex_reasoning"

    deployment:
      replicas: 1
      port: 11434  # Shared with realtime, Ollama handles model switching
      model_keep_alive: "5m"  # Shorter, da weniger frequent

# =========================================================================
# MODEL ROUTING CONFIGURATION
# =========================================================================
routing:
  default_model: "qwen3-8b"

  rules:
    # Real-Time Context
    - condition:
        context_type: "realtime"
      model: "qwen3-8b"

    # Simple Queries
    - condition:
        query_complexity: "simple"
        keywords: ["was ist", "wann", "wieviel", "letzte", "aktuelle"]
      model: "qwen3-8b"

    # Complex Analysis
    - condition:
        query_complexity: "complex"
        keywords: ["analysiere", "vergleiche", "trend", "zusammenfassung", "report"]
      model: "qwen3-14b"

    # Batch Jobs (immer 14B)
    - condition:
        context_type: "batch"
      model: "qwen3-14b"

    # Long Context (>50k tokens)
    - condition:
        context_tokens_gt: 50000
      model: "qwen3-14b"
      thinking_mode: true
```

### 3.2 Chunking Strategy

```yaml
# config/chunking.yaml
# Optimierte Chunking-Konfiguration für deutsche Geschäftsdokumente

chunking:
  # Default Settings
  default:
    chunk_size: 512        # Tokens
    chunk_overlap: 50      # Tokens
    min_chunk_size: 100    # Minimum Tokens

  # Document-Type Specific
  document_types:
    # Rechnungen - kleinere Chunks für präzise Extraktion
    rechnung:
      chunk_size: 256
      chunk_overlap: 25
      preserve_tables: true
      extract_metadata:
        - "Rechnungsnummer"
        - "Rechnungsdatum"
        - "Betrag"
        - "MwSt"
        - "Lieferant"

    # Verträge - größere Chunks für Kontext
    vertrag:
      chunk_size: 1024
      chunk_overlap: 100
      preserve_sections: true
      section_markers:
        - "§"
        - "Artikel"
        - "Abschnitt"
      extract_metadata:
        - "Vertragsparteien"
        - "Vertragsbeginn"
        - "Vertragsende"
        - "Kündigungsfrist"

    # Lieferscheine
    lieferschein:
      chunk_size: 256
      chunk_overlap: 25
      preserve_tables: true

    # Korrespondenz / Briefe
    korrespondenz:
      chunk_size: 512
      chunk_overlap: 50
      preserve_paragraphs: true

    # Technische Dokumentation
    technisch:
      chunk_size: 768
      chunk_overlap: 75
      preserve_code_blocks: true
      preserve_lists: true

  # Semantic Splitting (zusätzlich zu Size-based)
  semantic_splitting:
    enabled: true
    split_on:
      - "\n\n"           # Paragraph breaks
      - "\n§"            # Section markers
      - "\nArtikel"
      - "---"            # Horizontal rules
    max_chunk_size: 2048  # Hard limit auch bei semantic split
```

---

## 4. Service Architecture

### 4.1 Python Package Structure

```
src/
├── rag/
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py            # Pydantic models
│   │   ├── database.py           # SQLAlchemy models
│   │   └── enums.py              # Enum definitions
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── embedding_service.py  # Embedding generation
│   │   ├── search_service.py     # Semantic search
│   │   ├── reranker_service.py   # Result reranking
│   │   ├── llm_service.py        # LLM inference
│   │   ├── chat_service.py       # Chat management
│   │   ├── customer_card_service.py
│   │   └── report_service.py     # Report generation
│   │
│   ├── chunking/
│   │   ├── __init__.py
│   │   ├── base_chunker.py       # Abstract base
│   │   ├── semantic_chunker.py   # Semantic splitting
│   │   ├── document_chunker.py   # Document-type aware
│   │   └── table_chunker.py      # Table handling
│   │
│   ├── routing/
│   │   ├── __init__.py
│   │   ├── model_router.py       # Model selection logic
│   │   └── query_analyzer.py     # Query complexity analysis
│   │
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── prompt_templates.py   # Prompt management
│   │   ├── excel_generator.py    # openpyxl integration
│   │   ├── pdf_generator.py      # reportlab/weasyprint
│   │   └── word_generator.py     # python-docx
│   │
│   ├── batch/
│   │   ├── __init__.py
│   │   ├── job_scheduler.py      # Job scheduling
│   │   ├── customer_card_job.py  # Card generation job
│   │   ├── reembedding_job.py    # Reembedding job
│   │   └── report_job.py         # Scheduled reports
│   │
│   └── api/
│       ├── __init__.py
│       ├── router.py             # FastAPI router
│       ├── endpoints/
│       │   ├── search.py
│       │   ├── chat.py
│       │   ├── customer_cards.py
│       │   └── reports.py
│       └── dependencies.py       # FastAPI dependencies
```

### 4.2 Core Service Implementations

#### 4.2.1 Embedding Service

```python
# src/rag/services/embedding_service.py
"""
Embedding Service für das Ablage-System RAG Layer.

Verantwortlich für:
- Generierung von Embeddings für Dokumente und Queries
- Batch-Processing für große Dokumentmengen
- Caching von häufigen Embeddings
"""

from typing import List, Optional
import httpx
import numpy as np
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..models.schemas import EmbeddingRequest, EmbeddingResponse


class EmbeddingService:
    """Service für Text-zu-Embedding Konvertierung."""

    def __init__(
        self,
        endpoint_url: str = None,
        model_name: str = "intfloat/multilingual-e5-large",
        timeout: float = 30.0,
    ):
        self.endpoint_url = endpoint_url or settings.EMBEDDING_SERVICE_URL
        self.model_name = model_name
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def embed_single(self, text: str) -> List[float]:
        """
        Generiert Embedding für einen einzelnen Text.

        Args:
            text: Der zu embedende Text

        Returns:
            List[float]: 1024-dimensionaler Embedding-Vektor

        Raises:
            EmbeddingError: Bei Fehlern in der Embedding-Generierung
        """
        # Prefix für E5 Modelle (wichtig für Performance!)
        prefixed_text = f"passage: {text}"

        response = await self._client.post(
            f"{self.endpoint_url}/embed",
            json={"inputs": prefixed_text}
        )
        response.raise_for_status()

        return response.json()[0]

    async def embed_query(self, query: str) -> List[float]:
        """
        Generiert Embedding für eine Suchanfrage.

        Wichtig: Queries bekommen anderen Prefix als Dokumente!
        """
        prefixed_query = f"query: {query}"

        response = await self._client.post(
            f"{self.endpoint_url}/embed",
            json={"inputs": prefixed_query}
        )
        response.raise_for_status()

        return response.json()[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Batch-Embedding für große Dokumentmengen.

        Args:
            texts: Liste der zu embedenden Texte
            batch_size: Größe der Batches für API-Calls
            show_progress: Progress-Bar anzeigen

        Returns:
            Liste von Embedding-Vektoren
        """
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            prefixed_batch = [f"passage: {t}" for t in batch]

            response = await self._client.post(
                f"{self.endpoint_url}/embed",
                json={"inputs": prefixed_batch}
            )
            response.raise_for_status()

            embeddings.extend(response.json())

        return embeddings

    async def close(self):
        """Schließt den HTTP Client."""
        await self._client.aclose()
```

#### 4.2.2 Search Service

```python
# src/rag/services/search_service.py
"""
Search Service für semantische Dokumentensuche.

Implementiert:
- Pure Semantic Search via pgvector
- Hybrid Search (Semantic + Keyword)
- Reranking der Ergebnisse
"""

from typing import List, Optional, Tuple
from uuid import UUID
import asyncpg
from pydantic import BaseModel

from ..config import settings
from .embedding_service import EmbeddingService
from .reranker_service import RerankerService


class SearchResult(BaseModel):
    """Einzelnes Suchergebnis."""
    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    page_number: Optional[int]
    section_type: Optional[str]
    similarity_score: float
    rerank_score: Optional[float] = None


class SearchService:
    """Service für semantische Dokumentensuche."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        embedding_service: EmbeddingService,
        reranker_service: Optional[RerankerService] = None,
    ):
        self.db = db_pool
        self.embeddings = embedding_service
        self.reranker = reranker_service

    async def semantic_search(
        self,
        query: str,
        limit: int = 20,
        threshold: float = 0.7,
        document_ids: Optional[List[UUID]] = None,
        section_types: Optional[List[str]] = None,
        rerank: bool = True,
        rerank_top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Führt semantische Suche durch.

        Args:
            query: Suchanfrage in natürlicher Sprache
            limit: Maximale Anzahl Ergebnisse
            threshold: Minimale Similarity (0-1)
            document_ids: Optional - nur in diesen Dokumenten suchen
            section_types: Optional - nur in diesen Sections suchen
            rerank: Reranking aktivieren
            rerank_top_k: Anzahl Ergebnisse für Reranking

        Returns:
            Liste von SearchResult, sortiert nach Relevanz
        """
        # 1. Query Embedding generieren
        query_embedding = await self.embeddings.embed_query(query)

        # 2. Vector Search in PostgreSQL
        results = await self._vector_search(
            query_embedding=query_embedding,
            limit=limit if not rerank else limit * 2,  # Mehr holen für Reranking
            threshold=threshold,
            document_ids=document_ids,
            section_types=section_types,
        )

        # 3. Optional: Reranking
        if rerank and self.reranker and len(results) > 0:
            results = await self._rerank_results(
                query=query,
                results=results,
                top_k=rerank_top_k,
            )

        return results[:limit]

    async def hybrid_search(
        self,
        query: str,
        limit: int = 20,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        rerank: bool = True,
    ) -> List[SearchResult]:
        """
        Kombinierte Semantic + Keyword Suche.

        Nützlich wenn exakte Begriffe wichtig sind (z.B. Rechnungsnummern).
        """
        query_embedding = await self.embeddings.embed_query(query)

        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM rag_hybrid_search($1, $2, $3, $4, $5)
                """,
                query_embedding,
                query,
                semantic_weight,
                keyword_weight,
                limit * 2 if rerank else limit,
            )

        results = [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                chunk_text=row["chunk_text"],
                page_number=None,
                section_type=None,
                similarity_score=row["combined_score"],
            )
            for row in rows
        ]

        if rerank and self.reranker:
            results = await self._rerank_results(query, results, limit)

        return results[:limit]

    async def _vector_search(
        self,
        query_embedding: List[float],
        limit: int,
        threshold: float,
        document_ids: Optional[List[UUID]],
        section_types: Optional[List[str]],
    ) -> List[SearchResult]:
        """Interne Methode für pgvector Suche."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM rag_semantic_search($1, $2, $3, $4, $5)
                """,
                query_embedding,
                threshold,
                limit,
                document_ids,
                section_types,
            )

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                chunk_text=row["chunk_text"],
                page_number=row["page_number"],
                section_type=row["section_type"],
                similarity_score=row["similarity"],
            )
            for row in rows
        ]

    async def _rerank_results(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """Rerankt Ergebnisse mit Cross-Encoder."""
        if not results:
            return results

        # Reranker aufrufen
        rerank_scores = await self.reranker.rerank(
            query=query,
            documents=[r.chunk_text for r in results],
        )

        # Scores zuweisen und sortieren
        for result, score in zip(results, rerank_scores):
            result.rerank_score = score

        results.sort(key=lambda x: x.rerank_score or 0, reverse=True)

        return results[:top_k]
```

#### 4.2.3 LLM Service

```python
# src/rag/services/llm_service.py
"""
LLM Service für Inference mit Ollama.

Features:
- Model Routing (Real-Time vs. Analysis)
- Streaming Support
- Thinking Mode Control
- Context Management
"""

from typing import AsyncGenerator, List, Optional, Dict, Any
from enum import Enum
import httpx
from pydantic import BaseModel

from ..config import settings
from ..routing.model_router import ModelRouter
from ..routing.query_analyzer import QueryAnalyzer


class LLMModel(str, Enum):
    """Verfügbare LLM Modelle."""
    QWEN3_8B = "qwen3:8b-q4_K_M"
    QWEN3_14B = "qwen3:14b-q4_K_M"


class ChatMessage(BaseModel):
    """Chat Nachricht."""
    role: str  # "user", "assistant", "system"
    content: str


class LLMResponse(BaseModel):
    """LLM Antwort."""
    content: str
    model: str
    thinking_content: Optional[str] = None
    tokens_input: int
    tokens_output: int
    generation_time_ms: int


class LLMService:
    """Service für LLM Inference."""

    def __init__(
        self,
        ollama_url: str = None,
        model_router: Optional[ModelRouter] = None,
        query_analyzer: Optional[QueryAnalyzer] = None,
    ):
        self.ollama_url = ollama_url or settings.OLLAMA_URL
        self.router = model_router or ModelRouter()
        self.analyzer = query_analyzer or QueryAnalyzer()
        self._client = httpx.AsyncClient(timeout=120.0)

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[LLMModel] = None,
        context_type: str = "general",
        enable_thinking: bool = True,
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Generiert eine LLM Antwort.

        Args:
            messages: Chat-Verlauf
            model: Spezifisches Modell (oder auto-routing)
            context_type: "realtime" oder "batch"
            enable_thinking: Thinking Mode aktivieren
            temperature: Sampling Temperature
            max_tokens: Maximum Output Tokens

        Returns:
            LLMResponse mit generiertem Text
        """
        import time
        start_time = time.time()

        # Model Routing wenn nicht explizit angegeben
        if model is None:
            user_query = messages[-1].content if messages else ""
            model = self.router.select_model(
                query=user_query,
                context_type=context_type,
            )

        # Thinking Mode Prefix hinzufügen
        processed_messages = self._prepare_messages(
            messages,
            enable_thinking=enable_thinking
        )

        # Ollama API Call
        response = await self._client.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": model.value,
                "messages": [m.model_dump() for m in processed_messages],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        # Response parsen
        content = data["message"]["content"]
        thinking_content = None

        # Thinking Content extrahieren wenn vorhanden
        if "<think>" in content and "</think>" in content:
            think_start = content.find("<think>") + len("<think>")
            think_end = content.find("</think>")
            thinking_content = content[think_start:think_end].strip()
            content = content[think_end + len("</think>"):].strip()

        generation_time = int((time.time() - start_time) * 1000)

        return LLMResponse(
            content=content,
            model=model.value,
            thinking_content=thinking_content,
            tokens_input=data.get("prompt_eval_count", 0),
            tokens_output=data.get("eval_count", 0),
            generation_time_ms=generation_time,
        )

    async def generate_stream(
        self,
        messages: List[ChatMessage],
        model: Optional[LLMModel] = None,
        context_type: str = "general",
        enable_thinking: bool = False,  # Streaming meist ohne Thinking
    ) -> AsyncGenerator[str, None]:
        """
        Streaming Generation für Real-Time Responses.

        Yields:
            Token für Token der generierten Antwort
        """
        if model is None:
            model = self.router.select_model(
                query=messages[-1].content if messages else "",
                context_type=context_type,
            )

        processed_messages = self._prepare_messages(
            messages,
            enable_thinking=enable_thinking,
        )

        async with self._client.stream(
            "POST",
            f"{self.ollama_url}/api/chat",
            json={
                "model": model.value,
                "messages": [m.model_dump() for m in processed_messages],
                "stream": True,
            },
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]

    def _prepare_messages(
        self,
        messages: List[ChatMessage],
        enable_thinking: bool,
    ) -> List[ChatMessage]:
        """Bereitet Messages für das Model vor."""
        if not messages:
            return messages

        # Kopie erstellen
        prepared = [ChatMessage(**m.model_dump()) for m in messages]

        # Thinking Mode Instruction
        if enable_thinking:
            # Füge /think zum letzten User-Message hinzu
            for i in range(len(prepared) - 1, -1, -1):
                if prepared[i].role == "user":
                    if "/think" not in prepared[i].content and "/no_think" not in prepared[i].content:
                        prepared[i].content = f"{prepared[i].content} /think"
                    break
        else:
            # Füge /no_think hinzu
            for i in range(len(prepared) - 1, -1, -1):
                if prepared[i].role == "user":
                    if "/think" not in prepared[i].content and "/no_think" not in prepared[i].content:
                        prepared[i].content = f"{prepared[i].content} /no_think"
                    break

        return prepared

    async def close(self):
        """Schließt HTTP Client."""
        await self._client.aclose()
```

#### 4.2.4 Customer Card Service

```python
# src/rag/services/customer_card_service.py
"""
Customer Card Service für Pre-Computed Kunden-Zusammenfassungen.

Ermöglicht:
- Instant-Zugriff auf Kundendaten am Telefon
- Nächtliche Aktualisierung aller Cards
- Inkrementelle Updates bei neuen Dokumenten
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import asyncpg
from pydantic import BaseModel

from ..config import settings
from .search_service import SearchService
from .llm_service import LLMService, ChatMessage, LLMModel
from ..generation.prompt_templates import CUSTOMER_CARD_PROMPT


class CustomerCard(BaseModel):
    """Kundenkarte mit allen relevanten Informationen."""
    customer_id: str
    customer_name: str
    customer_type: Optional[str]

    summary_text: str
    quick_facts: List[str]

    open_invoices: List[Dict[str, Any]]
    active_contracts: List[Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]

    total_revenue_ytd: Optional[float]
    total_revenue_last_year: Optional[float]
    average_order_value: Optional[float]
    payment_behavior: Optional[str]

    flags: List[str]
    priority_level: int

    last_sync_at: datetime
    source_document_count: int


class CustomerCardService:
    """Service für Customer Cards."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        search_service: SearchService,
        llm_service: LLMService,
    ):
        self.db = db_pool
        self.search = search_service
        self.llm = llm_service

    async def get_card(self, customer_id: str) -> Optional[CustomerCard]:
        """
        Holt Customer Card aus der Datenbank.

        Optimiert für schnellen Zugriff (< 100ms).
        """
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM rag_customer_cards
                WHERE customer_id = $1
                """,
                customer_id,
            )

        if not row:
            return None

        return CustomerCard(
            customer_id=row["customer_id"],
            customer_name=row["customer_name"],
            customer_type=row["customer_type"],
            summary_text=row["summary_text"],
            quick_facts=row["quick_facts"],
            open_invoices=row["open_invoices"],
            active_contracts=row["active_contracts"],
            recent_orders=row["recent_orders"],
            total_revenue_ytd=row["total_revenue_ytd"],
            total_revenue_last_year=row["total_revenue_last_year"],
            average_order_value=row["average_order_value"],
            payment_behavior=row["payment_behavior"],
            flags=row["flags"],
            priority_level=row["priority_level"],
            last_sync_at=row["last_full_sync_at"] or row["updated_at"],
            source_document_count=row["source_document_count"],
        )

    async def search_customers(
        self,
        query: str,
        limit: int = 10,
    ) -> List[CustomerCard]:
        """
        Sucht Kunden nach Name (Fuzzy Search).

        Verwendet pg_trgm für schnelle Fuzzy-Suche.
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM rag_customer_cards
                WHERE customer_name % $1
                ORDER BY similarity(customer_name, $1) DESC
                LIMIT $2
                """,
                query,
                limit,
            )

        return [
            CustomerCard(
                customer_id=row["customer_id"],
                customer_name=row["customer_name"],
                # ... (alle Felder)
            )
            for row in rows
        ]

    async def generate_card(
        self,
        customer_id: str,
        customer_name: str,
    ) -> CustomerCard:
        """
        Generiert eine neue Customer Card mittels LLM.

        Wird im Batch-Job oder bei Bedarf aufgerufen.
        """
        # 1. Alle relevanten Dokumente zum Kunden finden
        search_results = await self.search.semantic_search(
            query=f"Kunde {customer_name} {customer_id}",
            limit=100,
            threshold=0.6,
            rerank=True,
            rerank_top_k=50,
        )

        if not search_results:
            # Keine Dokumente gefunden - Basis-Card erstellen
            return await self._create_empty_card(customer_id, customer_name)

        # 2. Context aus Dokumenten zusammenstellen
        context = self._build_context(search_results)

        # 3. LLM für Summary und Analyse
        messages = [
            ChatMessage(
                role="system",
                content=CUSTOMER_CARD_PROMPT,
            ),
            ChatMessage(
                role="user",
                content=f"""
                Erstelle eine Kundenübersicht für:

                Kunde: {customer_name}
                Kundennummer: {customer_id}

                Relevante Dokumente:
                {context}

                Antworte im folgenden JSON-Format:
                {{
                    "summary": "...",
                    "quick_facts": ["...", "..."],
                    "open_invoices": [...],
                    "active_contracts": [...],
                    "recent_orders": [...],
                    "payment_behavior": "...",
                    "flags": [...],
                    "priority_level": 0-10
                }}
                """,
            ),
        ]

        response = await self.llm.generate(
            messages=messages,
            model=LLMModel.QWEN3_14B,  # Immer großes Modell für Card-Generierung
            context_type="batch",
            enable_thinking=True,
        )

        # 4. Response parsen
        import json
        try:
            card_data = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback: Einfache Card
            card_data = {
                "summary": response.content[:500],
                "quick_facts": [],
                "open_invoices": [],
                "active_contracts": [],
                "recent_orders": [],
                "payment_behavior": "Unbekannt",
                "flags": [],
                "priority_level": 0,
            }

        # 5. In Datenbank speichern
        card = CustomerCard(
            customer_id=customer_id,
            customer_name=customer_name,
            customer_type=self._classify_customer(card_data),
            summary_text=card_data.get("summary", ""),
            quick_facts=card_data.get("quick_facts", []),
            open_invoices=card_data.get("open_invoices", []),
            active_contracts=card_data.get("active_contracts", []),
            recent_orders=card_data.get("recent_orders", []),
            total_revenue_ytd=None,  # Wird separat berechnet
            total_revenue_last_year=None,
            average_order_value=None,
            payment_behavior=card_data.get("payment_behavior"),
            flags=card_data.get("flags", []),
            priority_level=card_data.get("priority_level", 0),
            last_sync_at=datetime.utcnow(),
            source_document_count=len(search_results),
        )

        await self._save_card(card, [r.document_id for r in search_results])

        return card

    def _build_context(self, results) -> str:
        """Baut Context-String aus Suchergebnissen."""
        context_parts = []
        for i, result in enumerate(results[:30], 1):  # Max 30 für Context
            context_parts.append(
                f"[Dokument {i}]\n{result.chunk_text}\n"
            )
        return "\n---\n".join(context_parts)

    def _classify_customer(self, card_data: Dict) -> str:
        """Klassifiziert Kundentyp basierend auf Daten."""
        if len(card_data.get("recent_orders", [])) > 10:
            return "Stammkunde"
        elif len(card_data.get("recent_orders", [])) > 0:
            return "Aktivkunde"
        else:
            return "Neukunde"

    async def _save_card(
        self,
        card: CustomerCard,
        source_document_ids: List[UUID],
    ):
        """Speichert Card in Datenbank."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_customer_cards (
                    customer_id, customer_name, customer_type,
                    summary_text, quick_facts,
                    open_invoices, active_contracts, recent_orders,
                    total_revenue_ytd, total_revenue_last_year,
                    average_order_value, payment_behavior,
                    flags, priority_level,
                    last_full_sync_at, sync_status,
                    source_document_ids, source_document_count
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, 'completed', $16, $17
                )
                ON CONFLICT (customer_id) DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    customer_type = EXCLUDED.customer_type,
                    summary_text = EXCLUDED.summary_text,
                    quick_facts = EXCLUDED.quick_facts,
                    open_invoices = EXCLUDED.open_invoices,
                    active_contracts = EXCLUDED.active_contracts,
                    recent_orders = EXCLUDED.recent_orders,
                    payment_behavior = EXCLUDED.payment_behavior,
                    flags = EXCLUDED.flags,
                    priority_level = EXCLUDED.priority_level,
                    last_full_sync_at = EXCLUDED.last_full_sync_at,
                    sync_status = 'completed',
                    source_document_ids = EXCLUDED.source_document_ids,
                    source_document_count = EXCLUDED.source_document_count,
                    updated_at = NOW()
                """,
                card.customer_id,
                card.customer_name,
                card.customer_type,
                card.summary_text,
                card.quick_facts,
                card.open_invoices,
                card.active_contracts,
                card.recent_orders,
                card.total_revenue_ytd,
                card.total_revenue_last_year,
                card.average_order_value,
                card.payment_behavior,
                card.flags,
                card.priority_level,
                card.last_sync_at,
                source_document_ids,
                card.source_document_count,
            )

    async def _create_empty_card(
        self,
        customer_id: str,
        customer_name: str,
    ) -> CustomerCard:
        """Erstellt leere Card wenn keine Dokumente gefunden."""
        return CustomerCard(
            customer_id=customer_id,
            customer_name=customer_name,
            customer_type="Neukunde",
            summary_text="Keine Dokumente zu diesem Kunden gefunden.",
            quick_facts=[],
            open_invoices=[],
            active_contracts=[],
            recent_orders=[],
            total_revenue_ytd=None,
            total_revenue_last_year=None,
            average_order_value=None,
            payment_behavior=None,
            flags=[],
            priority_level=0,
            last_sync_at=datetime.utcnow(),
            source_document_count=0,
        )
```

---

## 5. API Endpoints

### 5.1 FastAPI Router

```python
# src/rag/api/router.py
"""
FastAPI Router für RAG Intelligence Layer.

Alle Endpoints unter /api/v1/rag/
"""

from fastapi import APIRouter

from .endpoints import search, chat, customer_cards, reports

router = APIRouter(prefix="/api/v1/rag", tags=["RAG Intelligence"])

# Include sub-routers
router.include_router(search.router, prefix="/search", tags=["Search"])
router.include_router(chat.router, prefix="/chat", tags=["Chat"])
router.include_router(customer_cards.router, prefix="/customers", tags=["Customers"])
router.include_router(reports.router, prefix="/reports", tags=["Reports"])
```

### 5.2 Search Endpoints

```python
# src/rag/api/endpoints/search.py
"""
Search API Endpoints.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ...services.search_service import SearchService, SearchResult
from ..dependencies import get_search_service

router = APIRouter()


class SearchRequest(BaseModel):
    """Request für semantische Suche."""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    document_ids: Optional[List[UUID]] = None
    section_types: Optional[List[str]] = None
    rerank: bool = True
    hybrid: bool = False


class SearchResponse(BaseModel):
    """Response für Suche."""
    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: int


@router.post("/", response_model=SearchResponse)
async def semantic_search(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service),
):
    """
    Semantische Dokumentensuche.

    Durchsucht alle OCR-verarbeiteten Dokumente nach relevanten Inhalten.
    """
    import time
    start = time.time()

    if request.hybrid:
        results = await search_service.hybrid_search(
            query=request.query,
            limit=request.limit,
            rerank=request.rerank,
        )
    else:
        results = await search_service.semantic_search(
            query=request.query,
            limit=request.limit,
            threshold=request.threshold,
            document_ids=request.document_ids,
            section_types=request.section_types,
            rerank=request.rerank,
        )

    return SearchResponse(
        query=request.query,
        results=results,
        total_results=len(results),
        search_time_ms=int((time.time() - start) * 1000),
    )
```

### 5.3 Chat Endpoints

```python
# src/rag/api/endpoints/chat.py
"""
Chat API Endpoints.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...services.chat_service import ChatService
from ...services.llm_service import ChatMessage
from ..dependencies import get_chat_service

router = APIRouter()


class ChatRequest(BaseModel):
    """Request für Chat."""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[UUID] = None
    context_type: str = Field(default="general")  # "general", "customer", "document"
    context_id: Optional[str] = None  # z.B. customer_id
    realtime: bool = Field(default=False)  # Für Telefon-Support
    stream: bool = Field(default=False)


class ChatResponse(BaseModel):
    """Response für Chat."""
    session_id: UUID
    message: str
    sources: List[dict]
    model_used: str
    thinking_content: Optional[str]
    generation_time_ms: int


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Chat mit dem Document Intelligence System.

    - Für allgemeine Fragen zu Dokumenten
    - Für kundenspezifische Anfragen (context_type="customer")
    - Für Dokument-Analyse (context_type="document")
    """
    if request.stream:
        return StreamingResponse(
            chat_service.chat_stream(
                message=request.message,
                session_id=request.session_id,
                context_type=request.context_type,
                context_id=request.context_id,
                realtime=request.realtime,
            ),
            media_type="text/event-stream",
        )

    response = await chat_service.chat(
        message=request.message,
        session_id=request.session_id,
        context_type=request.context_type,
        context_id=request.context_id,
        realtime=request.realtime,
    )

    return response


@router.get("/sessions/{session_id}/history")
async def get_chat_history(
    session_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
):
    """Holt Chat-Verlauf einer Session."""
    return await chat_service.get_history(session_id)
```

### 5.4 Customer Card Endpoints

```python
# src/rag/api/endpoints/customer_cards.py
"""
Customer Card API Endpoints.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...services.customer_card_service import CustomerCardService, CustomerCard
from ..dependencies import get_customer_card_service

router = APIRouter()


@router.get("/{customer_id}", response_model=CustomerCard)
async def get_customer_card(
    customer_id: str,
    service: CustomerCardService = Depends(get_customer_card_service),
):
    """
    Holt Customer Card für schnellen Telefon-Support.

    Latenz: < 100ms
    """
    card = await service.get_card(customer_id)
    if not card:
        raise HTTPException(status_code=404, detail="Customer not found")
    return card


@router.get("/search/", response_model=List[CustomerCard])
async def search_customers(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    service: CustomerCardService = Depends(get_customer_card_service),
):
    """
    Sucht Kunden nach Name (Fuzzy Search).
    """
    return await service.search_customers(query=q, limit=limit)


@router.post("/{customer_id}/refresh")
async def refresh_customer_card(
    customer_id: str,
    customer_name: str,
    service: CustomerCardService = Depends(get_customer_card_service),
):
    """
    Aktualisiert Customer Card manuell.

    Wird normalerweise durch Batch-Job gemacht.
    """
    return await service.generate_card(customer_id, customer_name)
```

---

## 6. Docker Deployment

### 6.1 Docker Compose

```yaml
# docker-compose.rag.yaml
# RAG Intelligence Layer Services

version: "3.9"

services:
  # =========================================================================
  # EMBEDDING SERVICE
  # Text Embeddings Inference von HuggingFace
  # =========================================================================
  embedding-service:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
    container_name: ablage-embedding
    command: >
      --model-id intfloat/multilingual-e5-large
      --port 8080
      --max-concurrent-requests 64
    ports:
      - "8081:8080"
    volumes:
      - embedding-cache:/data
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HF_TOKEN:-}
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - ablage-network

  # =========================================================================
  # RERANKER SERVICE
  # Cross-Encoder für bessere Suchergebnisse
  # =========================================================================
  reranker-service:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
    container_name: ablage-reranker
    command: >
      --model-id BAAI/bge-reranker-v2-m3
      --port 8080
    ports:
      - "8082:8080"
    volumes:
      - reranker-cache:/data
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HF_TOKEN:-}
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - ablage-network

  # =========================================================================
  # OLLAMA LLM SERVICE
  # Lokale LLM Inference für Qwen3 Modelle
  # =========================================================================
  ollama:
    image: ollama/ollama:latest
    container_name: ablage-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama-models:/root/.ollama
      - ./scripts/ollama-init.sh:/init.sh:ro
    environment:
      - OLLAMA_KEEP_ALIVE=24h
      - OLLAMA_NUM_PARALLEL=2
      - OLLAMA_MAX_LOADED_MODELS=2
    deploy:
      resources:
        limits:
          memory: 32G
        reservations:
          memory: 16G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 5
    restart: unless-stopped
    networks:
      - ablage-network

  # =========================================================================
  # OLLAMA MODEL LOADER
  # Lädt die benötigten Modelle beim Start
  # =========================================================================
  ollama-loader:
    image: curlimages/curl:latest
    container_name: ablage-ollama-loader
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        echo "Waiting for Ollama to be ready..."
        sleep 10

        echo "Pulling Qwen3-8B for real-time inference..."
        curl -X POST http://ollama:11434/api/pull -d '{"name": "qwen3:8b-q4_K_M"}'

        echo "Pulling Qwen3-14B for deep analysis..."
        curl -X POST http://ollama:11434/api/pull -d '{"name": "qwen3:14b-q4_K_M"}'

        echo "Models loaded successfully!"
    networks:
      - ablage-network

volumes:
  embedding-cache:
    driver: local
  reranker-cache:
    driver: local
  ollama-models:
    driver: local

networks:
  ablage-network:
    external: true
    name: ablage-system_default
```

### 6.2 Environment Variables

```bash
# .env.rag
# Environment Variablen für RAG Layer

# =========================================================================
# SERVICE URLS
# =========================================================================
EMBEDDING_SERVICE_URL=http://embedding-service:8080
RERANKER_SERVICE_URL=http://reranker-service:8080
OLLAMA_URL=http://ollama:11434

# =========================================================================
# MODEL CONFIGURATION
# =========================================================================
DEFAULT_EMBEDDING_MODEL=intfloat/multilingual-e5-large
DEFAULT_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
DEFAULT_LLM_REALTIME=qwen3:8b-q4_K_M
DEFAULT_LLM_ANALYSIS=qwen3:14b-q4_K_M

# =========================================================================
# RAG SETTINGS
# =========================================================================
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=50
RAG_SEARCH_LIMIT=20
RAG_SEARCH_THRESHOLD=0.7
RAG_RERANK_ENABLED=true
RAG_RERANK_TOP_K=10

# =========================================================================
# CUSTOMER CARDS
# =========================================================================
CUSTOMER_CARD_SYNC_ENABLED=true
CUSTOMER_CARD_SYNC_CRON="0 3 * * *"  # Täglich um 3 Uhr
CUSTOMER_CARD_SYNC_BATCH_SIZE=50

# =========================================================================
# PERFORMANCE
# =========================================================================
LLM_MAX_CONCURRENT_REQUESTS=4
EMBEDDING_BATCH_SIZE=32
SEARCH_CACHE_TTL=300  # 5 Minuten

# =========================================================================
# OPTIONAL: HUGGINGFACE TOKEN (für private Modelle)
# =========================================================================
HF_TOKEN=
```

---

## 7. Batch Processing

### 7.1 Customer Card Sync Job

```python
# src/rag/batch/customer_card_job.py
"""
Batch Job für nächtliche Customer Card Aktualisierung.

Läuft um 3 Uhr nachts, aktualisiert alle Kunden-Cards.
"""

import asyncio
from datetime import datetime
from typing import List
import asyncpg

from ..services.customer_card_service import CustomerCardService
from ..config import settings


class CustomerCardSyncJob:
    """Batch Job für Customer Card Synchronisation."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        card_service: CustomerCardService,
        batch_size: int = 50,
    ):
        self.db = db_pool
        self.card_service = card_service
        self.batch_size = batch_size

    async def run(self):
        """Führt den Sync Job aus."""
        job_id = await self._create_job_record()

        try:
            # 1. Alle unique Kunden aus Dokumenten ermitteln
            customers = await self._get_all_customers()
            total = len(customers)

            await self._update_job_progress(job_id, 0, f"Found {total} customers")

            # 2. In Batches verarbeiten
            processed = 0
            errors = []

            for i in range(0, total, self.batch_size):
                batch = customers[i:i + self.batch_size]

                for customer_id, customer_name in batch:
                    try:
                        await self.card_service.generate_card(
                            customer_id=customer_id,
                            customer_name=customer_name,
                        )
                        processed += 1
                    except Exception as e:
                        errors.append({
                            "customer_id": customer_id,
                            "error": str(e),
                        })

                progress = int((i + len(batch)) / total * 100)
                await self._update_job_progress(
                    job_id,
                    progress,
                    f"Processed {processed}/{total}",
                )

            # 3. Job abschließen
            await self._complete_job(
                job_id,
                result={
                    "total_customers": total,
                    "processed": processed,
                    "errors": errors,
                },
            )

        except Exception as e:
            await self._fail_job(job_id, str(e))
            raise

    async def _get_all_customers(self) -> List[tuple]:
        """Ermittelt alle unique Kunden aus den Dokumenten."""
        async with self.db.acquire() as conn:
            # Annahme: documents Tabelle hat customer_id und customer_name
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    metadata->>'customer_id' as customer_id,
                    metadata->>'customer_name' as customer_name
                FROM documents
                WHERE metadata->>'customer_id' IS NOT NULL
                ORDER BY metadata->>'customer_name'
                """
            )
        return [(r["customer_id"], r["customer_name"]) for r in rows]

    async def _create_job_record(self) -> str:
        """Erstellt Job-Record in der Datenbank."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO rag_batch_jobs (
                    job_type, job_name, status, started_at
                ) VALUES (
                    'customer_card_sync',
                    'Nightly Customer Card Sync',
                    'running',
                    NOW()
                ) RETURNING id
                """
            )
        return str(row["id"])

    async def _update_job_progress(
        self,
        job_id: str,
        progress: int,
        message: str,
    ):
        """Aktualisiert Job-Progress."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE rag_batch_jobs
                SET progress_percent = $1, progress_message = $2, updated_at = NOW()
                WHERE id = $3
                """,
                progress, message, job_id,
            )

    async def _complete_job(self, job_id: str, result: dict):
        """Markiert Job als abgeschlossen."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE rag_batch_jobs
                SET status = 'completed',
                    progress_percent = 100,
                    result = $1,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $2
                """,
                result, job_id,
            )

    async def _fail_job(self, job_id: str, error: str):
        """Markiert Job als fehlgeschlagen."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE rag_batch_jobs
                SET status = 'failed',
                    error_message = $1,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $2
                """,
                error, job_id,
            )
```

---

## 8. Report Generation

### 8.1 Excel Generator

```python
# src/rag/generation/excel_generator.py
"""
Excel Report Generator.

Erstellt professionelle Excel-Reports aus LLM-Analysen.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import io

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.chart import BarChart, Reference


class ExcelReportGenerator:
    """Generator für Excel Reports."""

    def __init__(self):
        self.wb = None

    def create_report(
        self,
        title: str,
        data: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> bytes:
        """
        Erstellt einen Excel-Report.

        Args:
            title: Report-Titel
            data: Strukturierte Daten für den Report
            output_path: Optional - Pfad zum Speichern

        Returns:
            Excel-File als Bytes
        """
        self.wb = Workbook()

        # Übersicht Sheet
        self._create_summary_sheet(title, data.get("summary", {}))

        # Daten Sheets
        for sheet_name, sheet_data in data.get("sheets", {}).items():
            self._create_data_sheet(sheet_name, sheet_data)

        # Charts wenn vorhanden
        if "charts" in data:
            self._create_charts(data["charts"])

        # Als Bytes exportieren
        buffer = io.BytesIO()
        self.wb.save(buffer)
        buffer.seek(0)

        if output_path:
            with open(output_path, "wb") as f:
                f.write(buffer.getvalue())

        return buffer.getvalue()

    def _create_summary_sheet(self, title: str, summary: Dict):
        """Erstellt Übersichts-Sheet."""
        ws = self.wb.active
        ws.title = "Übersicht"

        # Styling
        title_font = Font(size=18, bold=True)
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        # Titel
        ws["A1"] = title
        ws["A1"].font = title_font
        ws.merge_cells("A1:E1")

        # Generiert am
        ws["A2"] = f"Generiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

        # Summary Daten
        row = 4
        for key, value in summary.items():
            ws.cell(row=row, column=1, value=key).font = Font(bold=True)
            ws.cell(row=row, column=2, value=value)
            row += 1

        # Spaltenbreiten
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 40

    def _create_data_sheet(self, name: str, data: List[Dict]):
        """Erstellt Daten-Sheet mit Tabelle."""
        ws = self.wb.create_sheet(title=name[:31])  # Excel max 31 chars

        if not data:
            ws["A1"] = "Keine Daten verfügbar"
            return

        # Header
        headers = list(data[0].keys())
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Daten
        for row_idx, row_data in enumerate(data, 2):
            for col_idx, header in enumerate(headers, 1):
                value = row_data.get(header, "")
                ws.cell(row=row_idx, column=col_idx, value=value)

        # Auto-Fit Spaltenbreiten (approximiert)
        for col_idx, header in enumerate(headers, 1):
            max_length = len(str(header))
            for row_idx in range(2, len(data) + 2):
                cell_value = ws.cell(row=row_idx, column=col_idx).value
                if cell_value:
                    max_length = max(max_length, len(str(cell_value)))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_length + 2, 50)

    def _create_charts(self, charts_config: List[Dict]):
        """Erstellt Charts basierend auf Konfiguration."""
        for chart_config in charts_config:
            if chart_config.get("type") == "bar":
                self._add_bar_chart(chart_config)

    def _add_bar_chart(self, config: Dict):
        """Fügt Bar Chart hinzu."""
        ws = self.wb[config["sheet"]]

        chart = BarChart()
        chart.title = config.get("title", "")
        chart.x_axis.title = config.get("x_title", "")
        chart.y_axis.title = config.get("y_title", "")

        data = Reference(
            ws,
            min_col=config["data_col"],
            min_row=1,
            max_row=config["max_row"],
        )
        categories = Reference(
            ws,
            min_col=config["category_col"],
            min_row=2,
            max_row=config["max_row"],
        )

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)

        ws.add_chart(chart, config.get("position", "G2"))
```

### 8.2 PDF Generator

```python
# src/rag/generation/pdf_generator.py
"""
PDF Report Generator.

Erstellt professionelle PDF-Reports.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


class PDFReportGenerator:
    """Generator für PDF Reports."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Richtet Custom Styles ein."""
        self.styles.add(ParagraphStyle(
            name="CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor("#1F4E79"),
        ))

        self.styles.add(ParagraphStyle(
            name="SectionHeader",
            parent=self.styles["Heading2"],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor("#1F4E79"),
        ))

        self.styles.add(ParagraphStyle(
            name="BodyTextGerman",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=14,
        ))

    def create_report(
        self,
        title: str,
        content: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> bytes:
        """
        Erstellt einen PDF-Report.

        Args:
            title: Report-Titel
            content: Strukturierter Report-Inhalt
            output_path: Optional - Pfad zum Speichern

        Returns:
            PDF als Bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )

        story = []

        # Titel
        story.append(Paragraph(title, self.styles["CustomTitle"]))
        story.append(Paragraph(
            f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            self.styles["Normal"],
        ))
        story.append(Spacer(1, 20))

        # Executive Summary
        if "summary" in content:
            story.append(Paragraph("Executive Summary", self.styles["SectionHeader"]))
            story.append(Paragraph(content["summary"], self.styles["BodyTextGerman"]))
            story.append(Spacer(1, 20))

        # Sections
        for section in content.get("sections", []):
            story.append(Paragraph(section["title"], self.styles["SectionHeader"]))

            if "text" in section:
                story.append(Paragraph(section["text"], self.styles["BodyTextGerman"]))

            if "table" in section:
                story.append(self._create_table(section["table"]))

            if "bullet_points" in section:
                for point in section["bullet_points"]:
                    story.append(Paragraph(
                        f"• {point}",
                        self.styles["BodyTextGerman"],
                    ))

            story.append(Spacer(1, 15))

        # Build PDF
        doc.build(story)

        buffer.seek(0)
        pdf_bytes = buffer.getvalue()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes

    def _create_table(self, table_data: Dict) -> Table:
        """Erstellt formatierte Tabelle."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        data = [headers] + rows

        table = Table(data)
        table.setStyle(TableStyle([
            # Header Style
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),

            # Body Style
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),

            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

            # Alternating Rows
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),

            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        return table
```

---

## 9. Prompt Templates

```python
# src/rag/generation/prompt_templates.py
"""
Prompt Templates für verschiedene RAG Use Cases.

Alle Prompts sind für deutsche Geschäftsdokumente optimiert.
"""

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPT_GENERAL = """Du bist ein intelligenter Dokumenten-Assistent für ein deutsches Unternehmen.

Deine Aufgaben:
- Beantworte Fragen basierend auf den bereitgestellten Dokumenten
- Gib immer die Quellen (Dokumentennamen, Seitenzahlen) an
- Antworte präzise und auf Deutsch
- Bei Unsicherheit sage ehrlich, dass die Information nicht in den Dokumenten gefunden wurde

Formatierung:
- Nutze Aufzählungen für Listen
- Hebe wichtige Zahlen und Daten hervor
- Strukturiere längere Antworten mit Zwischenüberschriften
"""

SYSTEM_PROMPT_TELEFON = """Du bist ein schneller Telefon-Support-Assistent.

WICHTIG:
- Antworte KURZ und DIREKT
- Maximal 2-3 Sätze pro Antwort
- Nenne nur die wichtigsten Fakten
- Vermeide lange Erklärungen

Der Mitarbeiter ist am Telefon mit einem Kunden - Zeit ist kritisch!
"""

# =============================================================================
# CUSTOMER CARD PROMPT
# =============================================================================

CUSTOMER_CARD_PROMPT = """Du bist ein Analyst für Kundendaten.

Deine Aufgabe ist es, aus den bereitgestellten Dokumenten eine strukturierte Kundenübersicht zu erstellen.

Extrahiere folgende Informationen:
1. **Summary**: 2-3 Sätze Zusammenfassung der Kundenbeziehung
2. **Quick Facts**: 5-10 wichtige Stichpunkte
3. **Offene Rechnungen**: Liste mit Rechnungsnummer, Datum, Betrag, Status
4. **Aktive Verträge**: Liste mit Vertragsnummer, Typ, Laufzeit
5. **Letzte Bestellungen**: Die letzten 5 Bestellungen
6. **Zahlungsverhalten**: "Pünktlich", "Gelegentlich verzögert", "Problematisch"
7. **Flags**: Wichtige Warnungen oder Hinweise
8. **Priority Level**: 0-10 (10 = höchste Priorität)

Antworte NUR im angegebenen JSON-Format. Keine zusätzlichen Erklärungen.
"""

# =============================================================================
# REPORT GENERATION PROMPTS
# =============================================================================

REPORT_PROMPT_LIEFERANTEN = """Analysiere die Lieferantendaten und erstelle einen strukturierten Report.

Struktur des Reports:
1. **Executive Summary**: Wichtigste Erkenntnisse in 3-5 Sätzen
2. **Lieferanten-Übersicht**: Tabelle mit Name, Kategorie, Volumen, Trend
3. **Preisänderungen**: Analyse der Preisentwicklung
4. **Risiken**: Identifizierte Risiken (Abhängigkeiten, Preiserhöhungen)
5. **Empfehlungen**: Konkrete Handlungsempfehlungen

Antworte im JSON-Format für die automatische Report-Generierung.
"""

REPORT_PROMPT_VERTRAEGE = """Analysiere die Vertragsdaten und erstelle einen Compliance-Report.

Prüfe auf:
1. Auslaufende Verträge (nächste 90 Tage)
2. Fehlende Klauseln (GDPR, Haftung, Kündigungsfristen)
3. Ungewöhnliche Konditionen
4. Risiko-Einschätzung

Antworte im JSON-Format:
{
    "summary": "...",
    "expiring_contracts": [...],
    "compliance_issues": [...],
    "risk_assessment": {...},
    "recommendations": [...]
}
"""

# =============================================================================
# SEARCH QUERY ENHANCEMENT
# =============================================================================

QUERY_ENHANCEMENT_PROMPT = """Verbessere die folgende Suchanfrage für eine semantische Dokumentensuche.

Original: {query}

Erstelle 3 alternative Formulierungen die:
1. Synonyme und verwandte Begriffe enthalten
2. Typische deutsche Geschäftsbegriffe verwenden
3. Verschiedene Aspekte der Anfrage abdecken

Antworte als JSON-Array mit 3 Strings.
"""

# =============================================================================
# DOCUMENT CLASSIFICATION
# =============================================================================

CLASSIFICATION_PROMPT = """Klassifiziere das folgende Dokument.

Text (Ausschnitt):
{document_text}

Mögliche Kategorien:
- rechnung
- vertrag
- lieferschein
- angebot
- bestellung
- mahnung
- korrespondenz
- technisch
- sonstiges

Antworte NUR mit der Kategorie (ein Wort).
"""
```

---

## 10. Monitoring & Observability

### 10.1 Prometheus Metrics

```python
# src/rag/monitoring/metrics.py
"""
Prometheus Metrics für RAG Layer.
"""

from prometheus_client import Counter, Histogram, Gauge

# =============================================================================
# SEARCH METRICS
# =============================================================================

SEARCH_REQUESTS = Counter(
    "rag_search_requests_total",
    "Total number of search requests",
    ["search_type", "status"],  # semantic, hybrid, keyword | success, error
)

SEARCH_LATENCY = Histogram(
    "rag_search_latency_seconds",
    "Search request latency",
    ["search_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

SEARCH_RESULTS = Histogram(
    "rag_search_results_count",
    "Number of search results returned",
    buckets=[0, 1, 5, 10, 20, 50, 100],
)

# =============================================================================
# LLM METRICS
# =============================================================================

LLM_REQUESTS = Counter(
    "rag_llm_requests_total",
    "Total number of LLM requests",
    ["model", "context_type", "status"],
)

LLM_LATENCY = Histogram(
    "rag_llm_latency_seconds",
    "LLM request latency",
    ["model"],
    buckets=[1, 2, 5, 10, 20, 30, 60, 120],
)

LLM_TOKENS = Counter(
    "rag_llm_tokens_total",
    "Total tokens processed",
    ["model", "direction"],  # input, output
)

# =============================================================================
# EMBEDDING METRICS
# =============================================================================

EMBEDDING_REQUESTS = Counter(
    "rag_embedding_requests_total",
    "Total embedding requests",
    ["batch_size_bucket", "status"],
)

EMBEDDING_LATENCY = Histogram(
    "rag_embedding_latency_seconds",
    "Embedding generation latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# =============================================================================
# CUSTOMER CARDS METRICS
# =============================================================================

CUSTOMER_CARD_LOOKUPS = Counter(
    "rag_customer_card_lookups_total",
    "Customer card lookups",
    ["status"],  # hit, miss
)

CUSTOMER_CARD_SYNC_DURATION = Histogram(
    "rag_customer_card_sync_duration_seconds",
    "Customer card sync job duration",
    buckets=[60, 300, 600, 1800, 3600, 7200],
)

# =============================================================================
# SYSTEM METRICS
# =============================================================================

DOCUMENTS_EMBEDDED = Gauge(
    "rag_documents_embedded_total",
    "Total number of embedded document chunks",
)

MODEL_LOADED = Gauge(
    "rag_model_loaded",
    "Whether a model is currently loaded",
    ["model_name"],
)
```

### 10.2 Grafana Dashboard Config

```json
{
  "dashboard": {
    "title": "Ablage-System RAG Intelligence",
    "panels": [
      {
        "title": "Search Requests/min",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(rag_search_requests_total[1m])",
            "legendFormat": "{{search_type}}"
          }
        ]
      },
      {
        "title": "Search Latency P95",
        "type": "gauge",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(rag_search_latency_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "LLM Requests by Model",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(rag_llm_requests_total[5m])",
            "legendFormat": "{{model}}"
          }
        ]
      },
      {
        "title": "LLM Latency by Model",
        "type": "heatmap",
        "targets": [
          {
            "expr": "rate(rag_llm_latency_seconds_bucket[5m])"
          }
        ]
      },
      {
        "title": "Tokens Processed",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(increase(rag_llm_tokens_total[24h]))"
          }
        ]
      },
      {
        "title": "Customer Card Hit Rate",
        "type": "gauge",
        "targets": [
          {
            "expr": "sum(rate(rag_customer_card_lookups_total{status=\"hit\"}[5m])) / sum(rate(rag_customer_card_lookups_total[5m]))"
          }
        ]
      }
    ]
  }
}
```

---

## 11. Testing Strategy

### 11.1 Test Structure

```
tests/
├── rag/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   │
│   ├── unit/
│   │   ├── test_embedding_service.py
│   │   ├── test_search_service.py
│   │   ├── test_llm_service.py
│   │   ├── test_customer_card_service.py
│   │   ├── test_model_router.py
│   │   └── test_chunking.py
│   │
│   ├── integration/
│   │   ├── test_search_pipeline.py
│   │   ├── test_chat_flow.py
│   │   ├── test_report_generation.py
│   │   └── test_batch_jobs.py
│   │
│   └── e2e/
│       ├── test_telefon_support_scenario.py
│       └── test_report_workflow.py
```

### 11.2 Key Test Cases

```python
# tests/rag/unit/test_search_service.py
"""
Unit Tests für Search Service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.rag.services.search_service import SearchService, SearchResult


@pytest.fixture
def mock_db_pool():
    pool = AsyncMock()
    return pool


@pytest.fixture
def mock_embedding_service():
    service = AsyncMock()
    service.embed_query.return_value = [0.1] * 1024
    return service


@pytest.fixture
def search_service(mock_db_pool, mock_embedding_service):
    return SearchService(
        db_pool=mock_db_pool,
        embedding_service=mock_embedding_service,
    )


class TestSemanticSearch:
    """Tests für semantische Suche."""

    @pytest.mark.asyncio
    async def test_basic_search(self, search_service, mock_db_pool):
        """Test: Basis-Suche gibt Ergebnisse zurück."""
        # Arrange
        mock_db_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {
                "chunk_id": uuid4(),
                "document_id": uuid4(),
                "chunk_text": "Test Dokument Inhalt",
                "page_number": 1,
                "section_type": "paragraph",
                "similarity": 0.85,
            }
        ]

        # Act
        results = await search_service.semantic_search(
            query="Test Suche",
            limit=10,
        )

        # Assert
        assert len(results) == 1
        assert results[0].similarity_score == 0.85

    @pytest.mark.asyncio
    async def test_search_with_document_filter(self, search_service, mock_db_pool):
        """Test: Suche mit Dokument-Filter."""
        doc_id = uuid4()

        await search_service.semantic_search(
            query="Test",
            document_ids=[doc_id],
        )

        # Verify filter was passed
        call_args = mock_db_pool.acquire.return_value.__aenter__.return_value.fetch.call_args
        assert doc_id in call_args[0][3]  # document_ids parameter

    @pytest.mark.asyncio
    async def test_search_respects_threshold(self, search_service, mock_db_pool):
        """Test: Threshold filtert niedrige Scores."""
        mock_db_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = []

        results = await search_service.semantic_search(
            query="Test",
            threshold=0.9,  # Hoher Threshold
        )

        assert len(results) == 0


class TestHybridSearch:
    """Tests für Hybrid Search."""

    @pytest.mark.asyncio
    async def test_hybrid_combines_scores(self, search_service, mock_db_pool):
        """Test: Hybrid Search kombiniert Semantic + Keyword Scores."""
        mock_db_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {
                "chunk_id": uuid4(),
                "document_id": uuid4(),
                "chunk_text": "Test",
                "combined_score": 0.75,
                "semantic_score": 0.8,
                "keyword_score": 0.6,
            }
        ]

        results = await search_service.hybrid_search(
            query="Test Rechnung",
            semantic_weight=0.7,
            keyword_weight=0.3,
        )

        assert len(results) == 1
        assert results[0].similarity_score == 0.75
```

---

## 12. Migration Plan

### 12.1 Phase 1: Foundation (Woche 1-2)

```markdown
## Phase 1: Database & Infrastructure

### Tasks:
- [ ] PostgreSQL Extensions installieren (pgvector, pg_trgm)
- [ ] Database Migrationen erstellen und ausführen
- [ ] Docker Compose für Model Services erstellen
- [ ] Embedding Service deployen und testen
- [ ] Reranker Service deployen und testen
- [ ] Ollama mit Qwen3 Modellen einrichten

### Acceptance Criteria:
- [ ] `SELECT * FROM pg_extension WHERE extname = 'vector'` returns row
- [ ] Embedding Service Health Check: 200 OK
- [ ] Reranker Service Health Check: 200 OK
- [ ] `ollama list` zeigt beide Qwen3 Modelle
```

### 12.2 Phase 2: Core Services (Woche 3-4)

```markdown
## Phase 2: RAG Core Implementation

### Tasks:
- [ ] Embedding Service Python Client
- [ ] Chunking Pipeline implementieren
- [ ] Search Service mit pgvector
- [ ] Reranker Integration
- [ ] LLM Service mit Model Routing
- [ ] Unit Tests für alle Services

### Acceptance Criteria:
- [ ] Document Embedding Pipeline: 50 docs/min
- [ ] Semantic Search Latency: < 500ms (p95)
- [ ] Reranking Latency: < 100ms (p95)
- [ ] LLM Response (Qwen3-8B): < 15s
- [ ] Test Coverage: > 80%
```

### 12.3 Phase 3: Application Layer (Woche 5-6)

```markdown
## Phase 3: Application Features

### Tasks:
- [ ] Chat Service implementieren
- [ ] Customer Card Service implementieren
- [ ] Report Generator (Excel/PDF)
- [ ] Batch Job Scheduler
- [ ] API Endpoints
- [ ] Integration Tests

### Acceptance Criteria:
- [ ] Chat E2E Test: User Query → Response mit Quellen
- [ ] Customer Card Lookup: < 100ms
- [ ] Excel Report Generation: < 30s für 1000 rows
- [ ] PDF Report Generation: < 10s
- [ ] Nightly Batch Job läuft erfolgreich
```

### 12.4 Phase 4: Production Readiness (Woche 7-8)

```markdown
## Phase 4: Production Hardening

### Tasks:
- [ ] Prometheus Metrics
- [ ] Grafana Dashboards
- [ ] Error Handling & Retry Logic
- [ ] Rate Limiting
- [ ] Logging & Tracing
- [ ] Documentation
- [ ] E2E Tests
- [ ] Performance Tuning

### Acceptance Criteria:
- [ ] Grafana Dashboard zeigt alle Metriken
- [ ] Error Rate < 0.1%
- [ ] P99 Latency innerhalb SLOs
- [ ] Load Test: 100 concurrent users
- [ ] Documentation complete
```

---

## 13. Appendix

### 13.1 Hardware Requirements

| Deployment | CPU | RAM | Storage | Notes |
|------------|-----|-----|---------|-------|
| **Minimum** | 8 Cores | 32 GB | 100 GB SSD | Nur Qwen3-8B |
| **Recommended** | 16 Cores | 64 GB | 250 GB NVMe | Beide Modelle |
| **Enterprise** | 32 Cores | 128 GB | 500 GB NVMe | + Caching |

### 13.2 Performance Benchmarks (Target)

| Metrik | Target | Notes |
|--------|--------|-------|
| Embedding Latency | < 50ms | Single doc |
| Search Latency | < 500ms | Including rerank |
| Customer Card Lookup | < 100ms | Pre-computed |
| LLM Real-Time (8B) | < 15s | 300 token response |
| LLM Analysis (14B) | < 60s | 1000 token response |
| Batch Throughput | 50 cards/hour | Nightly sync |

### 13.3 Glossar

| Begriff | Beschreibung |
|---------|--------------|
| **RAG** | Retrieval-Augmented Generation - LLM mit externem Wissen |
| **Embedding** | Vektor-Repräsentation von Text |
| **pgvector** | PostgreSQL Extension für Vektorsuche |
| **Reranker** | Cross-Encoder für präzisere Relevanz-Scores |
| **Chunking** | Aufteilung von Dokumenten in kleinere Teile |
| **Customer Card** | Pre-computed Kundenzusammenfassung |
| **Thinking Mode** | Qwen3 Feature für Chain-of-Thought |

---

## 14. Changelog

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0.0 | 2025-12-03 | Initial Release |

---

**Dokument Ende**

*Dieses Dokument wurde für Claude Code / Opus erstellt und enthält alle notwendigen Informationen für die autonome Implementierung des RAG Intelligence Layers.*
