# Search API Documentation

## Uebersicht

Die Search-API ermoeglicht Volltextsuche und semantische Suche ueber alle Dokumente.
Unterstuetzt werden Keyword-Suche, Fuzzy-Matching und Vektor-basierte Aehnlichkeitssuche.

**Base URL:** `/api/v1/search`

## Authentifizierung

Alle Search-Endpoints erfordern:
- Gueltige JWT-Session

```bash
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/search/...
```

## Volltextsuche

### Einfache Suche

```http
GET /api/v1/search
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------
| q | string | - | Suchbegriff (erforderlich) |
| page | int | 1 | Seitennummer |
| limit | int | 20 | Ergebnisse pro Seite (max 100) |
| sort | string | relevance | Sortierung: relevance, date_asc, date_desc, name |
| highlight | bool | true | Treffer hervorheben |

**Response:**
```json
{
  "total": 42,
  "page": 1,
  "limit": 20,
  "query": "Rechnung 2024",
  "results": [
    {
      "document_id": "uuid",
      "filename": "rechnung_januar_2024.pdf",
      "relevance_score": 0.95,
      "highlight": {
        "content": "...die <em>Rechnung</em> fuer Januar <em>2024</em> betraegt..."
      },
      "created_at": "2024-01-15T10:30:00Z",
      "file_type": "application/pdf",
      "page_count": 2
    }
  ],
  "facets": {
    "file_types": [
      {"value": "application/pdf", "count": 30},
      {"value": "image/png", "count": 12}
    ],
    "date_ranges": [
      {"range": "last_week", "count": 5},
      {"range": "last_month", "count": 15},
      {"range": "last_year", "count": 42}
    ]
  }
}
```

### Erweiterte Suche

```http
POST /api/v1/search/advanced
```

**Request Body:**
```json
{
  "query": "Vertrag",
  "filters": {
    "file_types": ["application/pdf"],
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "tags": ["wichtig", "archiviert"],
    "ocr_confidence_min": 0.8
  },
  "options": {
    "fuzzy": true,
    "fuzzy_distance": 2,
    "phrase_match": false,
    "stem_german": true
  },
  "pagination": {
    "page": 1,
    "limit": 50
  },
  "sort": {
    "field": "relevance",
    "order": "desc"
  }
}
```

**Response:**
```json
{
  "total": 156,
  "page": 1,
  "limit": 50,
  "results": [
    {
      "document_id": "uuid",
      "filename": "mietvertrag_2024.pdf",
      "relevance_score": 0.98,
      "matched_fields": ["content", "filename"],
      "highlight": {
        "content": "...der <em>Vertrag</em> wird hiermit..."
      },
      "metadata": {
        "ocr_confidence": 0.95,
        "ocr_backend": "deepseek",
        "page_count": 5
      }
    }
  ],
  "query_info": {
    "parsed_query": "Vertrag",
    "applied_filters": 4,
    "execution_time_ms": 45
  }
}
```

## Semantische Suche

### Aehnlichkeitssuche (pgvector)

```http
POST /api/v1/search/semantic
```

**Request Body:**
```json
{
  "query": "Dokumente ueber Mietverhaeltnisse und Kuendigungsfristen",
  "limit": 10,
  "similarity_threshold": 0.7,
  "filters": {
    "file_types": ["application/pdf"],
    "date_from": "2023-01-01"
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "document_id": "uuid",
      "filename": "kuendigung_mietvertrag.pdf",
      "similarity_score": 0.92,
      "excerpt": "Die Kuendigungsfrist betraegt drei Monate zum Monatsende...",
      "embedding_model": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    }
  ],
  "query_embedding_generated": true,
  "execution_time_ms": 120
}
```

### Dokument-Aehnlichkeit finden

```http
GET /api/v1/search/similar/{document_id}
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------
| limit | int | 10 | Anzahl aehnlicher Dokumente |
| threshold | float | 0.6 | Minimale Aehnlichkeit (0-1) |

**Response:**
```json
{
  "source_document": {
    "id": "uuid",
    "filename": "rechnung_2024_01.pdf"
  },
  "similar_documents": [
    {
      "document_id": "uuid",
      "filename": "rechnung_2024_02.pdf",
      "similarity_score": 0.94,
      "shared_terms": ["Rechnung", "Betrag", "MwSt"]
    },
    {
      "document_id": "uuid",
      "filename": "rechnung_2023_12.pdf",
      "similarity_score": 0.89
    }
  ]
}
```

## Auto-Vervollstaendigung

### Suchvorschlaege

```http
GET /api/v1/search/suggest
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------
| q | string | - | Teilstring (min. 2 Zeichen) |
| limit | int | 10 | Max. Vorschlaege |

**Response:**
```json
{
  "suggestions": [
    {
      "text": "Rechnung 2024",
      "type": "query",
      "count": 42
    },
    {
      "text": "rechnung_januar_2024.pdf",
      "type": "filename",
      "document_id": "uuid"
    },
    {
      "text": "Rechnungswesen",
      "type": "tag",
      "count": 15
    }
  ]
}
```

## Suchverlauf

### Verlauf abrufen

```http
GET /api/v1/search/history
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------
| limit | int | 20 | Anzahl Eintraege |

**Response:**
```json
{
  "history": [
    {
      "query": "Rechnung 2024",
      "timestamp": "2024-12-02T10:30:00Z",
      "result_count": 42
    },
    {
      "query": "Mietvertrag",
      "timestamp": "2024-12-02T10:15:00Z",
      "result_count": 5
    }
  ]
}
```

### Verlauf loeschen

```http
DELETE /api/v1/search/history
```

**Response:**
```json
{
  "deleted_count": 50,
  "message": "Suchverlauf geloescht"
}
```

## Gespeicherte Suchen

### Suche speichern

```http
POST /api/v1/search/saved
```

**Request Body:**
```json
{
  "name": "Aktuelle Rechnungen",
  "query": "Rechnung",
  "filters": {
    "date_from": "2024-01-01",
    "file_types": ["application/pdf"]
  },
  "notify_on_new": true
}
```

**Response:**
```json
{
  "id": "uuid",
  "name": "Aktuelle Rechnungen",
  "created_at": "2024-12-02T10:30:00Z"
}
```

### Gespeicherte Suchen auflisten

```http
GET /api/v1/search/saved
```

**Response:**
```json
{
  "saved_searches": [
    {
      "id": "uuid",
      "name": "Aktuelle Rechnungen",
      "query": "Rechnung",
      "last_run": "2024-12-02T10:30:00Z",
      "new_results_count": 3
    }
  ]
}
```

### Gespeicherte Suche ausfuehren

```http
POST /api/v1/search/saved/{search_id}/run
```

**Response:** Wie Standard-Suchergebnis

### Gespeicherte Suche loeschen

```http
DELETE /api/v1/search/saved/{search_id}
```

## Such-Operatoren

### Unterstuetzte Syntax

| Operator | Beispiel | Beschreibung |
|----------|----------|--------------|
| AND | `Rechnung AND 2024` | Beide Begriffe muessen vorkommen |
| OR | `Rechnung OR Quittung` | Mindestens ein Begriff |
| NOT | `Vertrag NOT Kuendigung` | Begriff ausschliessen |
| "" | `"exakter Begriff"` | Exakte Phrase |
| * | `Rech*` | Wildcard (Praefix) |
| ~ | `Recnung~` | Fuzzy-Suche (Tippfehler) |
| ~N | `Recnung~2` | Fuzzy mit Edit-Distanz |

### Feldspezifische Suche

```
filename:rechnung
content:"Mehrwertsteuer"
tag:wichtig
date:[2024-01-01 TO 2024-12-31]
confidence:>0.8
```

## Filter-Optionen

### Verfuegbare Filter

```http
GET /api/v1/search/filters
```

**Response:**
```json
{
  "available_filters": {
    "file_types": [
      {"value": "application/pdf", "label": "PDF", "count": 1500},
      {"value": "image/png", "label": "PNG", "count": 300},
      {"value": "image/jpeg", "label": "JPEG", "count": 200}
    ],
    "tags": [
      {"value": "wichtig", "count": 50},
      {"value": "archiviert", "count": 200}
    ],
    "ocr_backends": [
      {"value": "deepseek", "count": 1000},
      {"value": "got_ocr", "count": 500},
      {"value": "surya", "count": 500}
    ],
    "date_ranges": [
      {"value": "today", "label": "Heute"},
      {"value": "last_week", "label": "Letzte Woche"},
      {"value": "last_month", "label": "Letzter Monat"},
      {"value": "last_year", "label": "Letztes Jahr"},
      {"value": "custom", "label": "Benutzerdefiniert"}
    ]
  }
}
```

## Batch-Suche

### Mehrere Abfragen gleichzeitig

```http
POST /api/v1/search/batch
```

**Request Body:**
```json
{
  "queries": [
    {"id": "q1", "query": "Rechnung 2024"},
    {"id": "q2", "query": "Vertrag Kuendigung"},
    {"id": "q3", "query": "filename:*.pdf"}
  ],
  "options": {
    "limit_per_query": 5
  }
}
```

**Response:**
```json
{
  "results": {
    "q1": {"total": 42, "results": [...]},
    "q2": {"total": 8, "results": [...]},
    "q3": {"total": 1500, "results": [...]}
  },
  "execution_time_ms": 150
}
```

## Re-Indexierung

### Index-Status (Admin)

```http
GET /api/v1/search/index/status
```

**Response:**
```json
{
  "total_documents": 2000,
  "indexed_documents": 1995,
  "pending_documents": 5,
  "last_full_reindex": "2024-12-01T02:00:00Z",
  "index_size_mb": 512,
  "embedding_coverage": 0.95
}
```

### Dokument neu indexieren (Admin)

```http
POST /api/v1/search/index/document/{document_id}
```

**Response:**
```json
{
  "document_id": "uuid",
  "status": "reindexed",
  "index_time_ms": 150
}
```

## Performance-Hinweise

### Optimale Suchanfragen

1. **Spezifische Begriffe**: Verwende konkrete Suchbegriffe
2. **Filter nutzen**: Reduziert Ergebnismenge erheblich
3. **Pagination**: Immer Limit setzen (max 100)
4. **Caching**: Identische Anfragen werden 5 Min gecached

### Rate Limits

| Endpoint | Limit |
|----------|-------|
| GET /search | 60/Min |
| POST /search/advanced | 30/Min |
| POST /search/semantic | 20/Min |
| POST /search/batch | 10/Min |

## Error Codes

| Code | Beschreibung |
|------|--------------|
| 400 | Ungueltige Suchanfrage |
| 401 | Nicht authentifiziert |
| 403 | Keine Berechtigung |
| 422 | Validierungsfehler (z.B. Query zu kurz) |
| 429 | Rate Limit erreicht |
| 500 | Interner Suchfehler |
| 503 | Suchindex nicht verfuegbar |

## Beispiel-Integration

### Python Client

```python
import httpx

async def search_documents(query: str, filters: dict = None):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/search/advanced",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": query,
                "filters": filters or {},
                "pagination": {"page": 1, "limit": 20}
            }
        )
        return response.json()

# Verwendung
results = await search_documents(
    "Rechnung",
    filters={"date_from": "2024-01-01"}
)
```

### cURL Beispiele

```bash
# Einfache Suche
curl "http://localhost:8000/api/v1/search?q=Rechnung&limit=10" \
  -H "Authorization: Bearer <token>"

# Semantische Suche
curl -X POST "http://localhost:8000/api/v1/search/semantic" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "Dokumente ueber Kuendigungsfristen", "limit": 5}'

# Aehnliche Dokumente
curl "http://localhost:8000/api/v1/search/similar/doc-uuid?limit=5" \
  -H "Authorization: Bearer <token>"
```
