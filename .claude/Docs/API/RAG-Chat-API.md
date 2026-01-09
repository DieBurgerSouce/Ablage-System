# RAG Chat API Documentation

> **Enterprise RAG (Retrieval Augmented Generation) System**
>
> Vollständige API-Dokumentation für das intelligente Chat-System mit semantischer Suche und LLM-Integration.

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Chat REST Endpoints](#2-chat-rest-endpoints)
3. [WebSocket API](#3-websocket-api)
4. [Search Endpoints](#4-search-endpoints)
5. [Chunking Endpoints](#5-chunking-endpoints)
6. [Batch Jobs](#6-batch-jobs)
7. [Request/Response Schemas](#7-requestresponse-schemas)
8. [Authentication & Rate Limiting](#8-authentication--rate-limiting)
9. [Service Architecture](#9-service-architecture)
10. [Best Practices](#10-best-practices)

---

## 1. Übersicht

### System-Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                      RAG Chat Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────┐         ┌──────────────────┐                 │
│  │  REST API     │         │  WebSocket API   │                 │
│  │  /api/v1/rag  │         │  /ws/chat/{id}   │                 │
│  └───────┬───────┘         └────────┬─────────┘                 │
│          │                          │                            │
│          ▼                          ▼                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                     ChatService                          │    │
│  │  ├── Message Processing                                  │    │
│  │  ├── Session Management                                  │    │
│  │  └── Context Retrieval                                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│          │                          │                            │
│          ▼                          ▼                            │
│  ┌─────────────────┐       ┌─────────────────┐                  │
│  │  SearchService  │       │   LLMService    │                  │
│  │  (RAG Context)  │       │   (Ollama)      │                  │
│  └────────┬────────┘       └────────┬────────┘                  │
│           │                         │                            │
│           ▼                         ▼                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Vector Storage (pgvector / Qdrant)          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Features

| Feature | Beschreibung |
|---------|--------------|
| Semantic Search | pgvector-basierte Chunk-Suche mit Reranking |
| LLM Integration | Ollama (lokal) mit intelligenter Model-Auswahl |
| Real-Time | WebSocket für Multi-User-Sessions |
| Session Management | Persistente Chat-Sessions mit Sharing |
| Document Chunking | Semantische Segmentierung mit Metadaten |

---

## 2. Chat REST Endpoints

**Basis-URL**: `/api/v1/rag/chat`

### 2.1 Chat Message senden

**POST** `/api/v1/rag/chat`

Sendet eine Chat-Nachricht (non-streaming).

**Rate Limit**: 30/Minute

```json
// Request
{
  "message": "Was steht in der Rechnung vom 15.01.2025?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",  // optional
  "context_type": "document",  // general|customer|document|report
  "context_id": "doc-12345",   // optional
  "realtime": false            // false = 14B Model, true = 8B Model
}

// Response 200
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Die Rechnung vom 15.01.2025 enthält...",
  "thinking_content": null,    // Chain-of-Thought (optional)
  "sources": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "doc-uuid",
      "chunk_text": "Rechnungsnummer: 2025-001...",
      "chunk_index": 3,
      "page_number": 1,
      "section_type": "paragraph",
      "similarity": 0.92,
      "rerank_score": 0.95
    }
  ],
  "model_used": "qwen3:14b",
  "generation_time_ms": 2340
}
```

### 2.2 Streaming Chat

**POST** `/api/v1/rag/chat/stream`

Server-Sent Events (SSE) für Token-by-Token Streaming.

**Rate Limit**: 20/Minute

```javascript
// Request (gleiche Struktur wie oben)

// Response: SSE Stream
event: chunk
data: {"chunk": "Die "}

event: chunk
data: {"chunk": "Rechnung "}

event: chunk
data: {"chunk": "enthält..."}

event: done
data: {"message_id": "msg-uuid", "full_content": "..."}

event: sources
data: {"sources": [...]}
```

### 2.3 Session erstellen

**POST** `/api/v1/rag/chat/sessions`

**Rate Limit**: 30/Minute

```json
// Request
{
  "title": "Rechnungsanalyse",     // optional
  "context_type": "document",       // optional
  "context_id": "doc-12345"         // optional
}

// Response 201
{
  "id": "session-uuid",
  "user_id": "user-uuid",
  "session_token": "tok_abc123",
  "title": "Rechnungsanalyse",
  "context_type": "document",
  "context_id": "doc-12345",
  "status": "active",
  "message_count": 0,
  "created_at": "2025-01-09T12:00:00Z",
  "updated_at": "2025-01-09T12:00:00Z",
  "last_message_at": null
}
```

### 2.4 Sessions auflisten

**GET** `/api/v1/rag/chat/sessions`

```json
// Query Parameters
?skip=0&limit=20&status=active

// Response 200
{
  "sessions": [...],
  "total": 42,
  "skip": 0,
  "limit": 20
}
```

### 2.5 Session Details

**GET** `/api/v1/rag/chat/sessions/{session_id}`

```json
// Response 200
{
  "id": "session-uuid",
  "title": "Rechnungsanalyse",
  "messages": [
    {
      "id": "msg-uuid",
      "role": "user",
      "content": "Was steht in der Rechnung?",
      "created_at": "2025-01-09T12:01:00Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Die Rechnung enthält...",
      "thinking_content": null,
      "model_used": "qwen3:14b",
      "generation_time_ms": 2340,
      "created_at": "2025-01-09T12:01:03Z"
    }
  ],
  "collaborators": [...],
  "status": "active"
}
```

### 2.6 Session aktualisieren

**PUT** `/api/v1/rag/chat/sessions/{session_id}`

**Rate Limit**: 60/Minute

```json
// Request
{
  "title": "Rechnungsanalyse Q1 2025"
}

// Response 200
{ /* Updated session */ }
```

### 2.7 Session löschen

**DELETE** `/api/v1/rag/chat/sessions/{session_id}`

**Rate Limit**: 30/Minute

```
Response: 204 No Content
```

### 2.8 Session teilen

**POST** `/api/v1/rag/chat/sessions/{session_id}/share`

**Rate Limit**: 20/Minute

```json
// Request
{
  "user_id": "target-user-uuid",
  "access_level": "contribute"  // view|contribute|manage
}

// Response 200
{
  "session_id": "session-uuid",
  "shared_with": "target-user-uuid",
  "access_level": "contribute"
}
```

### 2.9 Zugriff entziehen

**DELETE** `/api/v1/rag/chat/sessions/{session_id}/share/{user_id}`

**Rate Limit**: 20/Minute

```
Response: 204 No Content
```

### 2.10 Collaborators auflisten

**GET** `/api/v1/rag/chat/sessions/{session_id}/collaborators`

```json
// Response 200
{
  "collaborators": [
    {
      "user_id": "user-uuid",
      "username": "max.mustermann",
      "access_level": "contribute",
      "granted_at": "2025-01-09T12:00:00Z"
    }
  ]
}
```

---

## 3. WebSocket API

**Endpoint**: `ws://localhost:8000/ws/chat/{session_id}?token=<jwt_token>`

### 3.1 Verbindung

```javascript
const ws = new WebSocket(
  `ws://localhost:8000/ws/chat/${sessionId}?token=${jwtToken}`
);

ws.onopen = () => console.log('Connected');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleMessage(data);
};
```

### 3.2 Client → Server Messages

| Type | Payload | Beschreibung |
|------|---------|--------------|
| `typing_start` | `{}` | User tippt |
| `typing_stop` | `{}` | User hat aufgehört zu tippen |
| `ping` | `{}` | Keep-alive |
| `get_presence` | `{}` | Online-User anfragen |

```javascript
// Beispiel: Typing Indicator
ws.send(JSON.stringify({ type: 'typing_start' }));

// Nach 2 Sekunden ohne Eingabe
ws.send(JSON.stringify({ type: 'typing_stop' }));
```

### 3.3 Server → Client Messages

| Type | Payload | Beschreibung |
|------|---------|--------------|
| `user_joined` | `{user_id, username, timestamp}` | User verbunden |
| `user_left` | `{user_id, username, timestamp}` | User getrennt |
| `typing_start` | `{user_id, username}` | Anderer User tippt |
| `typing_stop` | `{user_id, username}` | Anderer User fertig |
| `presence` | `{users: [{user_id, username, is_typing}]}` | Online-Liste |
| `ai_chunk` | `{chunk: string}` | AI Response Chunk |
| `ai_done` | `{message_id, full_content}` | AI Response komplett |
| `error` | `{message: string}` | Fehlermeldung |
| `pong` | `{}` | Ping-Antwort |

```javascript
// Message Handler
function handleMessage(data) {
  switch (data.type) {
    case 'ai_chunk':
      appendToResponse(data.chunk);
      break;
    case 'ai_done':
      finalizeResponse(data.full_content);
      break;
    case 'typing_start':
      showTypingIndicator(data.username);
      break;
    case 'user_joined':
      addUserToList(data.username);
      break;
  }
}
```

---

## 4. Search Endpoints

**Basis-URL**: `/api/v1/rag/search`

### 4.1 Semantische Suche (POST)

**POST** `/api/v1/rag/search`

**Rate Limit**: 60/Minute

```json
// Request
{
  "query": "Rechnungsbetrag über 1000 Euro",
  "limit": 20,
  "threshold": 0.7,
  "document_ids": ["doc-1", "doc-2"],  // optional
  "section_types": ["paragraph", "table"],  // optional
  "search_type": "semantic",  // semantic|hybrid|keyword
  "rerank": true,
  "rerank_top_k": 10
}

// Response 200
{
  "query": "Rechnungsbetrag über 1000 Euro",
  "search_type": "semantic",
  "results": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "doc-uuid",
      "chunk_text": "Rechnungsbetrag: EUR 1.234,56...",
      "chunk_index": 5,
      "page_number": 1,
      "section_type": "paragraph",
      "similarity": 0.91,
      "rerank_score": 0.94
    }
  ],
  "total_results": 15,
  "search_time_ms": 145,
  "embedding_time_ms": 52,
  "rerank_time_ms": 89
}
```

### 4.2 Semantic Search (GET)

**GET** `/api/v1/rag/search/semantic`

```
?query=Rechnungsbetrag&limit=10&threshold=0.7
```

### 4.3 Hybrid Search (GET)

**GET** `/api/v1/rag/search/hybrid`

Kombiniert semantische Suche (70%) + Keyword-Suche (30%).

```
?query=Rechnung+2025-001&limit=10
```

### Search Types Vergleich

| Type | Beschreibung | Performance | Best For |
|------|--------------|-------------|----------|
| `semantic` | Vektor-Ähnlichkeit | ~100-200ms | Natürliche Sprache |
| `hybrid` | Semantic + FTS | ~150-300ms | Gemischte Queries |
| `keyword` | PostgreSQL FTS | ~50-100ms | Exakte Begriffe |

---

## 5. Chunking Endpoints

**Basis-URL**: `/api/v1/rag/chunks`

### 5.1 Dokument chunken

**POST** `/api/v1/rag/chunks/document/{document_id}`

```json
// Query Parameters
?strategy=semantic&chunk_size=512&overlap=50

// Response 200
{
  "document_id": "doc-uuid",
  "chunks_created": 24,
  "total_tokens": 12450,
  "processing_time_ms": 1234
}
```

**Chunking Strategies**:

| Strategy | Beschreibung |
|----------|--------------|
| `semantic` | Respektiert Satz-/Absatzgrenzen |
| `fixed` | Feste Chunk-Größe |
| `document_type` | Dokumenttyp-spezifisch |

### 5.2 Chunks abrufen

**GET** `/api/v1/rag/chunks/document/{document_id}`

```json
// Response 200
{
  "document_id": "doc-uuid",
  "chunks": [
    {
      "id": "chunk-uuid",
      "chunk_index": 0,
      "chunk_text": "Rechnung Nr. 2025-001...",
      "chunk_tokens": 256,
      "page_number": 1,
      "section_type": "header"
    }
  ],
  "total_chunks": 24
}
```

### 5.3 Bulk Chunking

**POST** `/api/v1/rag/chunks/bulk`

```json
// Request
{
  "document_ids": ["doc-1", "doc-2", "doc-3"],
  "strategy": "semantic",
  "chunk_size": 512
}

// Response 202
{
  "job_id": "job-uuid",
  "status": "processing",
  "total_documents": 3
}
```

---

## 6. Batch Jobs

**Basis-URL**: `/api/v1/rag/jobs`

### 6.1 Jobs auflisten

**GET** `/api/v1/rag/jobs`

```json
// Query Parameters
?status=processing&limit=20

// Response 200
{
  "jobs": [
    {
      "id": "job-uuid",
      "type": "bulk_chunking",
      "status": "processing",
      "progress": 45,
      "total_items": 100,
      "processed_items": 45,
      "created_at": "2025-01-09T12:00:00Z"
    }
  ]
}
```

### 6.2 Job Status

**GET** `/api/v1/rag/jobs/{job_id}`

```json
// Response 200
{
  "id": "job-uuid",
  "type": "bulk_chunking",
  "status": "completed",
  "progress": 100,
  "result": {
    "chunks_created": 1250,
    "errors": 0
  },
  "completed_at": "2025-01-09T12:05:00Z"
}
```

### 6.3 Job erstellen

**POST** `/api/v1/rag/jobs`

```json
// Request
{
  "type": "vector_sync",
  "params": {
    "document_ids": ["doc-1", "doc-2"]
  }
}

// Response 202
{
  "id": "job-uuid",
  "status": "pending"
}
```

### 6.4 Job abbrechen

**DELETE** `/api/v1/rag/jobs/{job_id}`

```
Response: 204 No Content
```

---

## 7. Request/Response Schemas

### RAGChatRequest

```typescript
interface RAGChatRequest {
  message: string;          // 1-10.000 Zeichen
  session_id?: string;      // UUID, optional
  context_type?: ContextType;
  context_id?: string;      // max 255 Zeichen
  realtime?: boolean;       // default: false
  stream?: boolean;         // default: false
}

type ContextType = 'general' | 'customer' | 'document' | 'report';
```

### RAGChatResponse

```typescript
interface RAGChatResponse {
  session_id: string;
  message: string;
  thinking_content?: string;
  sources: RAGChunkSource[];
  model_used: string;
  generation_time_ms: number;
}

interface RAGChunkSource {
  chunk_id: string;
  document_id: string;
  chunk_text: string;        // max 500 Zeichen
  chunk_index: number;
  page_number?: number;
  section_type?: SectionType;
  similarity: number;        // 0-1
  rerank_score?: number;     // 0-1
}

type SectionType = 'header' | 'paragraph' | 'table' | 'list' | 'footer';
```

### RAGSearchRequest

```typescript
interface RAGSearchRequest {
  query: string;             // 1-1.000 Zeichen
  limit?: number;            // 1-100, default: 20
  threshold?: number;        // 0-1, default: 0.7
  document_ids?: string[];   // Filter
  section_types?: SectionType[];
  search_type?: SearchType;  // default: 'semantic'
  rerank?: boolean;          // default: true
  rerank_top_k?: number;     // default: 10
}

type SearchType = 'semantic' | 'hybrid' | 'keyword';
```

### Session Schemas

```typescript
interface RAGChatSessionResponse {
  id: string;
  user_id: string;
  session_token: string;
  title?: string;
  context_type?: string;
  context_id?: string;
  status: SessionStatus;
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at?: string;
}

interface RAGChatMessageResponse {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  thinking_content?: string;
  confidence_score?: number;
  model_used?: string;
  tokens_input?: number;
  tokens_output?: number;
  generation_time_ms?: number;
  created_at: string;
  attached_document?: {
    id: string;
    name: string;
  };
}

type SessionStatus = 'active' | 'archived' | 'deleted';
type MessageRole = 'user' | 'assistant' | 'system';
```

---

## 8. Authentication & Rate Limiting

### Authentication

**Method**: JWT Bearer Token

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**WebSocket**: Query Parameter

```
ws://localhost:8000/ws/chat/{session_id}?token=eyJhbGciOiJIUzI1NiIs...
```

### Rate Limits

| Endpoint | Limit | Beschreibung |
|----------|-------|--------------|
| Chat Message | 30/min | LLM-intensiv |
| Chat Stream | 20/min | Streaming-Response |
| Search | 60/min | Embedding-Generierung |
| Session Create | 30/min | DB-Writes |
| Session Update | 60/min | Metadata-Updates |
| Session Share | 20/min | Permission-Änderungen |

### Error Responses

```json
// 401 Unauthorized
{
  "detail": "Token ungültig oder abgelaufen"
}

// 403 Forbidden
{
  "detail": "Kein Zugriff auf diese Session"
}

// 404 Not Found
{
  "detail": "Session nicht gefunden"
}

// 429 Too Many Requests
{
  "detail": "Rate limit überschritten. Bitte warten Sie 60 Sekunden.",
  "retry_after": 60
}
```

---

## 9. Service Architecture

### ChatService

**Datei**: `app/services/rag/chat_service.py`

```python
class ChatService:
    """Orchestriert Chat-Operationen."""

    async def chat(
        self,
        message: str,
        session_id: Optional[str],
        context_type: str,
        context_id: Optional[str],
        realtime: bool
    ) -> RAGChatResponse:
        """
        1. Session erstellen/laden
        2. Relevante Chunks suchen (RAG)
        3. LLM-Response generieren
        4. Message speichern
        5. Sources zurückgeben
        """
```

### LLMService

**Datei**: `app/services/rag/llm_service.py`

**Modelle**:
| Model | Context | Verwendung |
|-------|---------|------------|
| Qwen3:8b | Realtime | Schnell (<15s) |
| Qwen3:14b | Analysis | Detailliert |

**Context Types**:
| Type | Beschreibung |
|------|--------------|
| `GENERAL` | Standard-Dokumentfragen |
| `CUSTOMER` | Kundenspezifisch |
| `REPORT` | Report-Generierung |
| `REALTIME` | Telefon-Support (schnelles Model) |
| `EXTRACTION` | Datenextraktion |

**Thinking Mode**:
```python
# Qwen3 unterstützt <think>...</think> Tags
# Extrahiert und separat zurückgegeben
response = await llm.generate(
    prompt=prompt,
    enable_thinking=True  # default: False für Streaming
)
# thinking_content in Response enthalten
```

### SearchService (RAG)

**Datei**: `app/services/rag/search_service.py`

**Search Flow**:
```
Query
  │
  ├─► Embedding generieren (multilingual-e5-large)
  │
  ├─► Vector Search (pgvector/Qdrant)
  │     └─► Cosine Similarity
  │
  ├─► Optional: Keyword Search (PostgreSQL FTS)
  │     └─► Hybrid Scoring (70/30)
  │
  ├─► Threshold Filtering (default: 0.7)
  │
  └─► Optional: Reranking (BGE-Reranker)
        └─► Top-K Reordering
```

**Performance**:
- Embedding: ~50-100ms
- Vector Search: ~10-50ms
- Reranking: ~50-200ms pro Chunk

### ChunkingService

**Datei**: `app/services/rag/chunking_service.py`

**Strategien**:
| Strategy | Beschreibung |
|----------|--------------|
| `semantic` | Satz-/Absatzgrenzen |
| `fixed` | Feste Größe |
| `document_type` | Dokumenttyp-spezifisch |

**Konfiguration** (`config/chunking.yaml`):
```yaml
document_types:
  invoice:
    chunk_size: 400
    overlap: 50
  contract:
    chunk_size: 600
    overlap: 100
  default:
    chunk_size: 512
    overlap: 50
```

**Metadaten**:
- Page Number
- Section Type (header, paragraph, table, list, footer)
- Bounding Box (optional)
- Chunk Index
- Token Count

### VectorSyncService

**Datei**: `app/services/rag/vector_sync_service.py`

**Dual-Write Architektur**:
```
Document
    │
    ▼
ChunkingService
    │
    ├─► pgvector (Primary)
    │
    └─► Qdrant (A/B Testing)
```

**A/B Testing Status** (Januar 2026):
- Phase 1: 10% Traffic → Qdrant
- 674 Vektoren indexiert
- Migration: 10% → 25% → 50% → 100%

---

## 10. Best Practices

### 10.1 Chat-Integration

```typescript
// ✅ Session wiederverwenden
const sessionId = localStorage.getItem('chat_session_id');
const response = await chatApi.sendMessage({
  message: userInput,
  session_id: sessionId,  // Kontext erhalten
  context_type: 'document',
  context_id: currentDocumentId
});

// ❌ Jedes Mal neue Session
const response = await chatApi.sendMessage({
  message: userInput
  // Keine session_id = neuer Kontext
});
```

### 10.2 Streaming verwenden

```typescript
// ✅ Für bessere UX: Streaming
const eventSource = new EventSource('/api/v1/rag/chat/stream', {
  method: 'POST',
  body: JSON.stringify({ message: userInput })
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'chunk') {
    appendToUI(data.chunk);  // Sofort anzeigen
  }
};

// ❌ Auf komplette Response warten
const response = await fetch('/api/v1/rag/chat', {
  method: 'POST',
  body: JSON.stringify({ message: userInput })
});
// User wartet 3-5 Sekunden ohne Feedback
```

### 10.3 Context Type wählen

```typescript
// ✅ Passenden Context Type setzen
// Für Telefon-Support (schnell)
{ context_type: 'realtime', realtime: true }

// Für detaillierte Analyse
{ context_type: 'document', realtime: false }

// Für Kundenübersicht
{ context_type: 'customer', context_id: customerId }
```

### 10.4 Search Optimieren

```typescript
// ✅ Reranking für Top-Ergebnisse
const results = await searchApi.search({
  query: userQuery,
  limit: 20,
  rerank: true,
  rerank_top_k: 10  // Nur Top 10 reranken
});

// ✅ Hybrid für gemischte Queries
// "Rechnung 2025-001 über 1000 Euro"
{ search_type: 'hybrid' }

// ✅ Keyword für exakte Begriffe
// "INV-2025-001"
{ search_type: 'keyword' }
```

### 10.5 Error Handling

```typescript
try {
  const response = await chatApi.sendMessage(request);
} catch (error) {
  if (error.status === 429) {
    // Rate Limit - warten und erneut versuchen
    await sleep(error.retry_after * 1000);
    return sendMessage(request);
  }
  if (error.status === 401) {
    // Token abgelaufen - neu anmelden
    await refreshToken();
    return sendMessage(request);
  }
  // Andere Fehler dem User zeigen
  showError(error.detail);
}
```

---

## Database Models

### RAGChatSession

```sql
CREATE TABLE rag_chat_sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  session_token VARCHAR UNIQUE,
  title VARCHAR,
  context_type VARCHAR,
  context_id VARCHAR,
  status VARCHAR DEFAULT 'active',
  message_count INTEGER DEFAULT 0,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  last_message_at TIMESTAMP
);
```

### RAGChatMessage

```sql
CREATE TABLE rag_chat_messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES rag_chat_sessions(id),
  role VARCHAR,  -- user|assistant|system
  content TEXT,
  thinking_content TEXT,
  confidence_score FLOAT,
  model_used VARCHAR,
  tokens_input INTEGER,
  tokens_output INTEGER,
  generation_time_ms INTEGER,
  attached_document_id UUID,
  created_at TIMESTAMP
);
```

### RAGDocumentChunk

```sql
CREATE TABLE rag_document_chunks (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  chunk_index INTEGER,
  chunk_text TEXT,
  chunk_tokens INTEGER,
  page_number INTEGER,
  section_type VARCHAR,
  bounding_box JSONB,
  embedding VECTOR(1024),  -- pgvector
  embedding_model VARCHAR,
  embedding_created_at TIMESTAMP,
  qdrant_indexed_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

---

**Letzte Aktualisierung**: Januar 2026
**Version**: 1.0
**Maintainer**: Ablage-System Team
