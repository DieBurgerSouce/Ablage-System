# RAG Services

Retrieval-Augmented Generation (RAG) System fuer intelligente Dokumentensuche.

## Uebersicht

Das RAG-Modul ermoeglicht:
- Semantische Dokumentensuche ueber Vektoraehnlichkeit
- Hybrid-Suche (Vektor + Keyword)
- A/B-Testing zwischen pgvector und Qdrant
- Streaming Chat mit Kontext
- Multi-Collection Support

## Architektur

```
rag/
├── embedding_service.py        # Text zu Vektor Konvertierung
├── chunking_service.py         # Dokument-Chunking Strategien
├── qdrant_service.py           # Qdrant Vector Store
├── pgvector_service.py         # PostgreSQL pgvector Integration
├── hybrid_search_service.py    # Kombinierte Suche
├── reranking_service.py        # Cross-Encoder Reranking
├── chat_service.py             # Conversational RAG
└── models.py                   # Pydantic Schemas
```

## Komponenten

### Embedding Service

Unterstuetzt mehrere Embedding-Modelle:
- `sentence-transformers/all-MiniLM-L6-v2` (Default, 384 dim)
- `intfloat/multilingual-e5-base` (768 dim, mehrsprachig)
- `deepseek-ai/deepseek-coder-v2` (Code-optimiert)

```python
from app.services.rag.embedding_service import EmbeddingService

service = EmbeddingService()
embedding = await service.embed("Deutscher Dokumenttext")
# embedding.shape = (384,)
```

### Chunking Service

Strategien fuer Dokument-Segmentierung:
- **Semantic**: Absatz-basiert, behaelt Kontext
- **Fixed**: Feste Token-Anzahl mit Ueberlappung
- **Sliding Window**: Gleitendes Fenster fuer grosse Dokumente

```python
from app.services.rag.chunking_service import ChunkingService

service = ChunkingService(
    strategy="semantic",
    max_tokens=512,
    overlap=50
)
chunks = await service.chunk(document_text)
```

### Vector Stores

#### Qdrant (Empfohlen fuer Production)

```python
from app.services.rag.qdrant_service import QdrantService

service = QdrantService()
await service.index_document(doc_id, chunks, embeddings)
results = await service.search(query_embedding, limit=10)
```

#### pgvector (Fallback/A/B-Testing)

```python
from app.services.rag.pgvector_service import PgVectorService

service = PgVectorService()
await service.index_document(doc_id, chunks, embeddings)
results = await service.search(query_embedding, limit=10)
```

### Hybrid Search

Kombiniert Vektor- und Keyword-Suche:

```python
from app.services.rag.hybrid_search_service import HybridSearchService

service = HybridSearchService(
    vector_weight=0.7,
    keyword_weight=0.3
)
results = await service.search(
    query="Rechnungsbetrag 2024",
    filter_metadata={"doc_type": "invoice"}
)
```

### Chat Service

Konversationelle RAG mit Streaming:

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

## A/B-Testing

Das System unterstuetzt A/B-Tests zwischen Vector Stores:

```python
# Aktueller Traffic Split abfragen
GET /api/v1/metrics/ab-testing

# Traffic Split aendern (z.B. 30% Qdrant)
POST /api/v1/metrics/ab-testing/traffic-split?new_split=30
```

### Skalierungs-Roadmap

| Phase | Dokumente | Traffic Split | Backend |
|-------|-----------|---------------|---------|
| 1 (Aktuell) | 0 - 10k | 10% Qdrant | pgvector primary |
| 2 | 10k - 50k | 25-50% Qdrant | Parallel |
| 3 | 50k - 100k | 75-100% Qdrant | Migration |
| 4 | 100k+ | 100% Qdrant | Full Rollout |

## API Endpoints

```
POST /api/v1/rag/search          # Semantische Suche
POST /api/v1/rag/chat            # Single Chat Response
WS   /api/v1/rag/chat/stream     # WebSocket Streaming
GET  /api/v1/rag/chunks/{doc_id} # Chunks eines Dokuments
POST /api/v1/rag/reindex         # Dokument neu indizieren
```

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

## Tests

```bash
# Unit Tests
pytest tests/unit/services/rag/ -v

# Integration Tests (benoetigt Qdrant/PostgreSQL)
pytest tests/integration/rag/ -v

# Performance Tests
pytest tests/performance/rag/ -v --benchmark-only
```

## Performance-Optimierung

1. **Batch Embedding**: Verarbeite mehrere Texte gleichzeitig
2. **Index Tuning**: HNSW Parameter fuer Qdrant optimieren
3. **Caching**: Embedding-Cache fuer haeufige Anfragen
4. **Quantization**: Binary/Scalar Quantization fuer grosse Collections
