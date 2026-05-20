# RAG Services (Retrieval-Augmented Generation)

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält die RAG-Infrastruktur für intelligente Dokumentensuche und -analyse mit semantischem Retrieval und LLM-Integration.

Das RAG-Modul ermöglicht:
- Semantische Dokumentensuche über Vektorähnlichkeit
- Hybrid-Suche (Vektor + Keyword)
- A/B-Testing zwischen pgvector und Qdrant
- Streaming Chat mit Kontext
- Multi-Collection Support

---

## Services

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **RAGSearchService** | `search_service.py` | Semantische Chunk-Suche mit Reranking |
| **QdrantService** | `qdrant_service.py` | Qdrant Vector DB Integration |
| **ChatService** | `chat_service.py` | Document-aware Chat mit History |
| **ChunkingService** | `chunking_service.py` | Intelligentes Dokument-Chunking |
| **LLMService** | `llm_service.py` | Ollama LLM-Integration (Qwen3) |
| **VectorSyncService** | `vector_sync_service.py` | Dual-Write pgvector ↔ Qdrant |
| **ABTestingRouter** | `ab_testing_router.py` | A/B Testing für Search-Methoden |
| **AIActionService** | `ai_action_service.py` | Aktionsausführung basierend auf Chat |
| **CustomerCardService** | `customer_card_service.py` | Kundenkarten-Generierung |
| **ExcelGenerator** | `excel_generator.py` | Excel-Export für RAG-Ergebnisse |
| **WordGenerator** | `word_generator.py` | Word-Dokument-Generierung |
| **Metrics** | `metrics.py` | Prometheus-Metriken für RAG |
| **PromptTemplates** | `prompt_templates.py` | System-Prompts für LLM |

---

## RAGSearchService

Semantische Suche auf Dokumenten-Chunks.

### Suchtypen

| Typ | Beschreibung |
|-----|--------------|
| `semantic` | Vektor-Ähnlichkeitssuche |
| `hybrid` | Semantic + Keyword (FTS) |
| `keyword` | Nur Volltext-Suche |

### Features

- pgvector-basierte Ähnlichkeitssuche
- Optional: Reranking mit BGE-Reranker
- Query Enhancement via LLM
- Filterung nach Dokumenten, Sektionstypen

### Verwendung

```python
from app.services.rag.search_service import RAGSearchService

service = RAGSearchService()
response = await service.semantic_search(
    db=db,
    query="Welche Rechnungen sind überfällig?",
    limit=20,
    threshold=0.7,
    rerank=True
)
```

### SearchResult

```python
@dataclass
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    chunk_index: int
    page_number: Optional[int]
    section_type: Optional[str]
    similarity: float
    rerank_score: Optional[float]
```

---

## QdrantService

Enterprise Vector-DB Integration mit Qdrant.

### Features

| Feature | Beschreibung |
|---------|--------------|
| Connection Pooling | Health Checks, Auto-Reconnect |
| Collection Management | HNSW-Indexierung |
| Batch Operations | Effiziente Bulk-Inserts |
| Hybrid Search | Dense + Sparse Vectors |
| A/B Testing Support | Vergleich mit pgvector |

### Retry-Konfiguration

```python
QDRANT_MAX_RETRIES = 3
QDRANT_BASE_DELAY_SECONDS = 0.5
QDRANT_MAX_DELAY_SECONDS = 10.0
QDRANT_BACKOFF_MULTIPLIER = 2.0
```

### Verwendung

```python
from app.services.rag.qdrant_service import QdrantService

service = QdrantService()
await service.index_document(doc_id, chunks, embeddings)
results = await service.search(query_embedding, limit=10)
```

---

## ChatService

Document-aware Chat mit Kontext-Retrieval.

### Features

| Feature | Beschreibung |
|---------|--------------|
| Kontext-Retrieval | Automatische Dokumenten-Suche |
| Chat-History | Session-Management mit max. 20 Nachrichten |
| Streaming | Async Generator für Streaming-Responses |
| Quellenangaben | Referenzierte Dokumente werden zurückgegeben |

### ChatMessage

```python
class ChatMessage:
    id: str
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]
```

### ChatSession

```python
class ChatSession:
    id: str
    user_id: Optional[UUID]
    messages: List[ChatMessage]
    max_history: int = 20
    context_documents: List[Dict[str, Any]]
```

### Verwendung

```python
from app.services.rag.chat_service import ChatService

service = ChatService()
async for chunk in service.chat_stream(
    conversation_id="conv123",
    message="Was steht in der Rechnung vom 15.12.?",
    context_limit=5
):
    print(chunk, end="")
```

---

## ChunkingService

Intelligentes Chunking für optimale Retrieval-Performance.

### Chunking-Strategien

| Strategie | Beschreibung |
|-----------|--------------|
| Semantic | Absatz-basiert, behält Kontext |
| Fixed | Feste Token-Anzahl mit Überlappung |
| Sliding Window | Gleitendes Fenster für große Dokumente |
| Tabellen | Spezialbehandlung für Tabellen |
| Line-Items | Rechnungspositionen einzeln |

### ChunkConfig

```python
@dataclass
class ChunkConfig:
    chunk_size: int = 512
    overlap: int = 50
    min_chunk_size: int = 100
    max_chunk_size: int = 2048
    preserve_tables: bool = True
    preserve_paragraphs: bool = True
    preserve_sections: bool = False
    preserve_line_items: bool = False
    section_markers: List[str]
    extract_metadata: List[str]
```

### RAGSectionType

- `UNKNOWN` - Unbekannt
- `HEADER` - Kopfzeile
- `FOOTER` - Fußzeile
- `TABLE` - Tabelle
- `PARAGRAPH` - Absatz
- `LINE_ITEM` - Rechnungsposition
- `SUMMARY` - Zusammenfassung

### Verwendung

```python
from app.services.rag.chunking_service import ChunkingService

service = ChunkingService(
    strategy="semantic",
    max_tokens=512,
    overlap=50
)
chunks = await service.chunk(document_text)
```

---

## LLMService

Integration mit Ollama für lokale LLM-Inference.

### Unterstützte Modelle

| Modell | Verwendung | Latenz |
|--------|------------|--------|
| Qwen3-8B | Realtime-Anfragen | <15s |
| Qwen3-14B | Detaillierte Analysen | <60s |

### LLMContextType

| Typ | Beschreibung |
|-----|--------------|
| `general` | Allgemeine Dokumenten-Fragen |
| `customer` | Kunden-bezogene Anfragen |
| `report` | Report-Generierung |
| `realtime` | Schnelle Support-Antworten |
| `extraction` | Daten-Extraktion |

### LLMResponse

```python
@dataclass
class LLMResponse:
    content: str
    thinking_content: Optional[str]
    model: str
    tokens_input: int
    tokens_output: int
    generation_time_ms: int
    finish_reason: str
```

---

## VectorSyncService

Dual-Write Synchronisation zwischen pgvector und Qdrant.

### Sync-Modi

| Modus | Beschreibung |
|-------|--------------|
| Dual-Write | Beide DBs gleichzeitig |
| Async-Write | Qdrant asynchron im Hintergrund |
| Migration | Batch-Migration bestehender Daten |

### SyncStatus

- `pending` - Ausstehend
- `syncing` - In Synchronisation
- `synced` - Synchronisiert
- `failed` - Fehlgeschlagen
- `skipped` - Übersprungen

### Konfiguration

```python
VECTOR_DUAL_WRITE_ENABLED: bool    # Dual-Write aktiviert
VECTOR_DUAL_WRITE_ASYNC: bool      # Async-Modus
VECTOR_MIGRATION_BATCH_SIZE: int   # Batch-Größe (default: 100)
```

---

## ABTestingRouter

A/B Testing für verschiedene Search-Methoden.

### Features

- Traffic-Split konfigurierbar (z.B. 50/50)
- Metriken-Tracking (Latenz, Relevanz)
- Automatische Winner-Erkennung
- Rollout bei statistischer Signifikanz

### Skalierungs-Roadmap

| Phase | Dokumente | Traffic Split | Backend |
|-------|-----------|---------------|---------|
| 1 | 0 - 10k | 10% Qdrant | pgvector primary |
| 2 | 10k - 50k | 25-50% Qdrant | Parallel |
| 3 | 50k - 100k | 75-100% Qdrant | Migration |
| 4 | 100k+ | 100% Qdrant | Full Rollout |

---

## Embedding Service

Unterstützt mehrere Embedding-Modelle:

| Modell | Dimensionen | Beschreibung |
|--------|-------------|--------------|
| `all-MiniLM-L6-v2` | 384 | Default, schnell |
| `multilingual-e5-base` | 768 | Mehrsprachig (DE/EN) |
| `deepseek-coder-v2` | 768 | Code-optimiert |

```python
from app.services.embedding_service import get_embedding_service

service = get_embedding_service()
embedding = await service.embed("Deutscher Dokumenttext")
# embedding.shape = (384,)
```

---

## API Endpoints

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/api/v1/rag/search` | POST | Semantische Suche |
| `/api/v1/rag/chat` | POST | Chat-Nachricht senden |
| `/api/v1/rag/chat/stream` | WS | WebSocket Streaming |
| `/api/v1/rag/chat/{session_id}` | GET | Chat-History abrufen |
| `/api/v1/rag/chunks/{document_id}` | GET | Chunks eines Dokuments |
| `/api/v1/rag/reindex/{document_id}` | POST | Dokument neu indexieren |
| `/api/v1/rag/stats` | GET | RAG-Statistiken |
| `/api/v1/metrics/ab-testing` | GET | A/B-Test Status |
| `/api/v1/metrics/ab-testing/traffic-split` | POST | Traffic-Split ändern |

---

## Celery Tasks

| Task | Schedule | Beschreibung |
|------|----------|--------------|
| `rag.index_new_documents` | Kontinuierlich | Neue Dokumente indexieren |
| `rag.sync_to_qdrant` | Alle 5 Min | Qdrant-Synchronisation |
| `rag.cleanup_orphan_chunks` | Täglich 04:00 | Verwaiste Chunks entfernen |
| `rag.refresh_embeddings` | Wöchentlich | Embeddings aktualisieren |

---

## Datenmodell

### RAGDocumentChunk (PostgreSQL)

```python
id: UUID
document_id: UUID
chunk_index: int
chunk_text: str
tokens: int
page_number: Optional[int]
section_type: RAGSectionType
embedding: Vector(1536)       # pgvector
bounding_box: JSONB
metadata: JSONB
qdrant_synced: bool
created_at: DateTime
```

---

## Konfiguration

```env
# Embedding
RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_EMBEDDING_BATCH_SIZE=32

# Chunking
RAG_CHUNK_STRATEGY=semantic
RAG_CHUNK_MAX_TOKENS=512
RAG_CHUNK_OVERLAP=50

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=documents
QDRANT_REPLICATION_FACTOR=1

# pgvector
PGVECTOR_TABLE=document_embeddings
PGVECTOR_INDEX_LISTS=100

# Search
RAG_SEARCH_TOP_K=10
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

---

## Metriken

| Metrik | Beschreibung |
|--------|--------------|
| `rag_search_latency_seconds` | Such-Latenz |
| `rag_search_results_count` | Anzahl Ergebnisse |
| `rag_embedding_latency_seconds` | Embedding-Generierung |
| `rag_llm_latency_seconds` | LLM-Antwortzeit |
| `rag_chunks_indexed_total` | Indexierte Chunks |
| `rag_qdrant_sync_failures` | Sync-Fehler |

---

## Tests

```bash
# Unit Tests
pytest tests/unit/services/rag/ -v

# Integration Tests (benötigt Qdrant/PostgreSQL)
pytest tests/integration/rag/ -v

# Performance Tests
pytest tests/performance/rag/ -v --benchmark-only
```

---

## Best Practices

1. **Chunk-Größe**: 512 Tokens optimal für Retrieval
2. **Overlap**: 50 Tokens für Kontexterhalt
3. **Reranking**: Für bessere Relevanz aktivieren
4. **Hybrid Search**: Für exakte Begriffe + Semantik
5. **Caching**: Häufige Queries in Redis cachen
6. **Batch Embedding**: Mehrere Texte gleichzeitig verarbeiten
7. **Index Tuning**: HNSW-Parameter für Qdrant optimieren

---

## Sicherheit

1. **Tenant-Isolation**: Alle Queries via company_id gefiltert
2. **Input-Validierung**: Query-Länge begrenzt (max 1000 Zeichen)
3. **Rate Limiting**: Max 100 Searches/min
4. **PII-Schutz**: Keine sensiblen Daten in Logs
5. **Embedding-Sanitization**: XSS/Injection-Prevention
