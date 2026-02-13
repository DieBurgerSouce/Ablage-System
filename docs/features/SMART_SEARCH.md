# Feature #1: Smart Search / Natural Language Search

**Status**: Production-Ready
**Phase**: 2026 Q1
**Version**: 1.0.0

## Uebersicht

Intelligente Suche mit automatischer Erkennung von natuerlichsprachlichen Fragen vs. Keyword-Suche. Vereint NLQ, Hybrid-Suche und Entity-Suche in einem intelligenten Service.

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│                    Smart Search Service                  │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  1. Auto-Detection (NLQ vs. Keyword)                     │
│     ├─ Fragewort-Erkennung                               │
│     ├─ Aggregations-Muster                               │
│     ├─ Verb-Analyse                                      │
│     └─ Query-Laengen-Heuristik                           │
│                                                           │
│  2. Parallel Execution                                   │
│     ├─ NLQ Service (natuerliche Fragen)                  │
│     ├─ Unified Search (FTS + Semantic + Hybrid)          │
│     └─ Entity Search (Kunden/Lieferanten)                │
│                                                           │
│  3. Result Aggregation                                   │
│     ├─ Dokumente mit Scores                              │
│     ├─ Entities mit Confidence                           │
│     ├─ Facets/Aggregationen                              │
│     └─ Query Suggestions                                 │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Features

### 1. Automatische Query-Typ-Erkennung

**NLQ-Patterns:**
- Fragewoerter: "zeige", "finde", "wie viel", "welche", "wer", "was"
- Aggregationen: "summe", "durchschnitt", "anzahl", "gesamt"
- Verben: "sind", "haben", "kosten", "betraegt"
- Natuerliche Satzstruktur (5+ Woerter mit Verb)

**Keyword-Patterns:**
- Kurze Queries (1-2 Woerter)
- Boolean-Operatoren (AND, OR, NOT)
- Keine Fragewort-Muster
- Technische Suchbegriffe

**Beispiele:**

| Query | Erkannt als | Confidence | Reasoning |
|-------|-------------|------------|-----------|
| "Zeige alle Rechnungen von Mueller" | NLQ | 0.95 | Fragewort "zeige" |
| "Wie hoch ist die Summe" | NLQ | 0.90 | Aggregation "summe" |
| "Mueller Rechnung 2025" | Keyword | 0.90 | Kurze Query, keine Verb-Struktur |
| "invoice Mueller january" | Keyword | 0.80 | Keine NLQ-Muster |

### 2. Unified Search Integration

**Search Modes:**
- **NLQ Mode**: Natuerlichsprachliche Verarbeitung via NLQService
- **Keyword Mode**: Hybrid Search (FTS + Semantic via Unified Search)
- **Force Mode**: Manuelles Erzwingen eines Modus

**Search Types (Keyword Mode):**
- FTS (Full-Text Search): PostgreSQL tsvector
- Semantic: pgvector Cosine-Similarity
- Hybrid: RRF-Fusion beider Methoden

### 3. Entity Search (Parallel)

Wird **immer parallel** zur Haupt-Suche durchgefuehrt:

**Search Methods:**
- Kundennummer/Lieferantennummer (exakt)
- Matchcode (Fuzzy)
- IBAN/VAT-ID (validiert)
- Name/Alias (Similarity-Matching)

**Result Fields:**
- `entity_id`, `entity_type` (CUSTOMER/SUPPLIER)
- `name`, `display_name`
- `match_type` (customer_number, matchcode, iban, etc.)
- `confidence` (0.0-1.0)

### 4. Query Interpretation

Jede Suche gibt Interpretation zurueck:

```json
{
  "detected_type": "nlq",
  "confidence": 0.95,
  "reasoning": "Fragewort erkannt: 'zeige'",
  "nlq_intent": "search",
  "entities_found": ["Mueller GmbH", "Rechnung"]
}
```

### 5. Facets / Aggregationen

**Verfuegbare Facets:**
- `document_types`: {"invoice": 5, "contract": 2}
- `statuses`: {"pending": 3, "completed": 2}
- `date_ranges`: {"last_7_days": 5, "last_30_days": 10}
- `entities`: {"entity_id": count}

### 6. Query Suggestions

**Kontext-basierte Vorschlaege:**

Bei **keine Ergebnisse**:
- NLQ: "Versuchen Sie eine einfachere Formulierung"
- Keyword: "Verwenden Sie weniger spezifische Suchbegriffe"

Bei **Ergebnisse vorhanden**:
- NLQ: "Fragen Sie nach zusaetzlichen Details"
- Keyword: "Verfeinern Sie mit Dokumenttyp-Filter"

### 7. Autocomplete

Autocomplete-Vorschlaege basierend auf:
- Haeufigen NLQ-Patterns
- Query-History (erweiterbar)
- Entity-Namen (erweiterbar)

## API Endpoints

### POST /api/v1/smart-search

Haupt-Such-Endpoint mit Auto-Detection.

**Request:**
```json
{
  "query": "Zeige alle Rechnungen von Mueller",
  "filters": {
    "document_types": ["invoice"],
    "date_from": "2025-01-01",
    "date_to": "2025-12-31"
  },
  "limit": 20,
  "include_suggestions": true,
  "include_facets": true,
  "force_mode": null  // Optional: "nlq" oder "keyword"
}
```

**Response:**
```json
{
  "query": "Zeige alle Rechnungen von Mueller",
  "detected_type": "nlq",
  "interpretation": {
    "detected_type": "nlq",
    "confidence": 0.95,
    "reasoning": "Fragewort erkannt: 'zeige'",
    "nlq_intent": "search",
    "entities_found": ["Mueller"]
  },
  "documents": [
    {
      "document_id": "uuid",
      "filename": "Rechnung_Mueller_001.pdf",
      "score": 0.95,
      "document_type": "invoice",
      "status": "pending",
      "created_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total_documents": 1,
  "entities": [
    {
      "entity_id": "uuid",
      "entity_type": "CUSTOMER",
      "name": "Mueller GmbH",
      "match_type": "matchcode",
      "confidence": 0.90
    }
  ],
  "total_entities": 1,
  "natural_response": "Ich habe 1 Rechnung von Mueller GmbH gefunden.",
  "nlq_confidence": 0.85,
  "suggestions": [
    "Filtern Sie nach Datum",
    "Verfeinern Sie mit Status-Filter"
  ],
  "facets": {
    "document_types": {"invoice": 1},
    "statuses": {"pending": 1},
    "date_ranges": {"last_30_days": 1},
    "entities": {"uuid": 1},
    "total_count": 1
  },
  "search_time_ms": 45.2,
  "document_search_time_ms": 20.5,
  "entity_search_time_ms": 10.3,
  "nlq_processing_time_ms": 14.4
}
```

### GET /api/v1/smart-search/autocomplete

Autocomplete-Suggestions fuer Eingabe.

**Request:**
```
GET /api/v1/smart-search/autocomplete?q=Zeige&limit=10
```

**Response:**
```json
{
  "suggestions": [
    "Zeige alle Rechnungen von",
    "Zeige mir alle offenen",
    "Zeige Dokumente vom"
  ]
}
```

### GET /api/v1/smart-search/health

Health-Check fuer Service.

**Response:**
```json
{
  "status": "healthy",
  "service": "smart-search",
  "version": "1.0.0"
}
```

## Verwendung

### Python Service-Layer

```python
from app.services.smart_search_service import get_smart_search_service

service = get_smart_search_service()

# Auto-Detection
result = await service.search(
    db=db,
    query="Zeige alle Rechnungen von Mueller",
    user_id=user_id,
    company_id=company_id,
    limit=20,
)

print(f"Detected: {result.detected_type}")
print(f"Documents: {result.total_documents}")
print(f"Entities: {result.total_entities}")

# Force NLQ Mode
result_nlq = await service.search(
    db=db,
    query="Mueller invoice",
    user_id=user_id,
    force_mode=DetectedQueryType.NLQ,
)
```

### Frontend Integration (TypeScript)

```typescript
import { api } from '@/lib/api';

// Smart Search
const response = await api.post('/api/v1/smart-search', {
  query: searchQuery,
  filters: {
    document_types: ['invoice', 'contract'],
    date_from: '2025-01-01',
  },
  limit: 20,
  include_suggestions: true,
  include_facets: true,
});

// Autocomplete
const { suggestions } = await api.get('/api/v1/smart-search/autocomplete', {
  params: { q: partialQuery, limit: 10 },
});
```

## Performance

**Targets:**
- Total Search Time: <100ms (Keyword), <500ms (NLQ)
- Entity Search (parallel): <50ms
- Autocomplete: <20ms

**Metriken:**
- `smart_search_requests_total` - Counter by mode
- `smart_search_duration_seconds` - Histogram
- `smart_search_auto_detection_total` - Detection stats

## Konfiguration

```python
# app/core/config.py
class Settings(BaseSettings):
    # Search Settings
    HYBRID_FTS_WEIGHT: float = 0.5
    HYBRID_SEMANTIC_WEIGHT: float = 0.5
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5

    # NLQ Settings
    AUTONOMY_NLQ_ENABLED: bool = True
    AUTONOMY_NLQ_MAX_RESULTS: int = 100

    # Cache Settings
    SEARCH_CACHE_ENABLED: bool = True
    SEARCH_CACHE_TTL: int = 300  # 5 minutes
```

## Testing

```bash
# Unit Tests
pytest tests/unit/services/test_smart_search_service.py -v

# Integration Tests (requires DB)
pytest tests/integration/test_smart_search_integration.py -v

# Coverage
pytest --cov=app.services.smart_search_service --cov-report=html
```

## Security

### Multi-Tenancy
- Alle Queries sind company-scoped
- Entity-Suche respektiert company_presence
- Documents gefiltert nach company_id

### Rate Limiting
- Search Endpoint: 100/minute per User
- Autocomplete: 200/minute per User

### Input Validation
- Query max length: 500 characters
- Limit: 1-100
- Filters: Pydantic-validiert

## Known Issues & Limitations

1. **Auto-Detection Genauigkeit**: ~85-95% (abhaengig von Query)
   - Fallback: User kann force_mode nutzen

2. **NLQ Komplexitaet**: Limitiert auf vordefinierte Patterns
   - Enhancement: LLM-basierte Intent-Erkennung

3. **Facets Berechnung**: Nur auf Top-N Ergebnissen
   - Enhancement: Separate Facets-Aggregation-Query

4. **Autocomplete**: Aktuell nur statische Templates
   - Enhancement: Query-History Integration

## Future Enhancements

### Phase 2 (Q2 2026)
- [ ] LLM-basierte Intent-Erkennung
- [ ] Query-History fuer besseres Autocomplete
- [ ] Personalisierte Suggestions basierend auf User-Profil
- [ ] Multi-Language Support (Englisch)

### Phase 3 (Q3 2026)
- [ ] Voice Search Integration
- [ ] Image Search (OCR-Content)
- [ ] Collaborative Filtering fuer "Aehnliche Suchen"
- [ ] A/B Testing Framework fuer Auto-Detection

## Dependencies

- `app.services.ai.nlq_service` - NLQ Processing
- `app.services.unified_search_service` - Hybrid Search
- `app.services.entity_search_service` - Entity Search
- `app.services.query_expansion_service` - Synonym Expansion
- `app.services.embedding_service` - Semantic Embeddings

## Changelog

### v1.0.0 (2026-02-13)
- Initial Release
- Auto-Detection (NLQ vs. Keyword)
- Parallel Entity Search
- Facets & Suggestions
- Autocomplete Endpoint
- Comprehensive Tests

## Support

**Dokumentation**: `.claude/Docs/Features/Smart-Search.md`
**Tests**: `tests/unit/services/test_smart_search_service.py`
**Service**: `app/services/smart_search_service.py`
**API**: `app/api/v1/smart_search.py`

---

**Feinpoliert und durchdacht** - Deutsche Qualitaet 🇩🇪
