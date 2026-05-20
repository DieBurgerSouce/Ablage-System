# Smart Search - Quick Start Guide

5-Minuten Einführung für Entwickler

---

## Grundkonzept

Smart Search = **Ein Suchfeld für alles**

```
User tippt: "Zeige alle Rechnungen von Mueller"
         ↓
    Auto-Detection
         ↓
    NLQ erkannt? → Ja
         ↓
    NLQ Service
         ↓
    Ergebnis: 3 Rechnungen + Mueller GmbH Entity
```

---

## Quick Examples

### 1. Basic Search (Python)

```python
from app.services.smart_search_service import get_smart_search_service

service = get_smart_search_service()

result = await service.search(
    db=db,
    query="Zeige alle Rechnungen",
    user_id=user.id,
    company_id=user.company_id,
    limit=20,
)

print(f"Type: {result.detected_type}")  # "nlq"
print(f"Documents: {result.total_documents}")  # 5
print(f"Response: {result.natural_response}")  # "Ich habe 5 Rechnungen gefunden."
```

### 2. Force Mode

```python
# Force Keyword-Suche (auch wenn Query wie NLQ aussieht)
from app.services.smart_search_service import DetectedQueryType

result = await service.search(
    db=db,
    query="Zeige alle Rechnungen",  # Würde normalerweise NLQ erkennen
    user_id=user.id,
    force_mode=DetectedQueryType.KEYWORD,  # Erzwingt Keyword
)
```

### 3. With Filters

```python
from app.db.schemas import SearchFilters

filters = SearchFilters(
    document_types=["invoice", "contract"],
    date_from="2025-01-01",
    date_to="2025-12-31",
    statuses=["pending", "completed"],
)

result = await service.search(
    db=db,
    query="Mueller",
    user_id=user.id,
    filters=filters,
    limit=10,
)
```

### 4. Autocomplete

```python
suggestions = await service.autocomplete(
    db=db,
    query="Zeige",  # Partial input
    limit=5,
)

# Returns: ["Zeige alle Rechnungen von", "Zeige mir alle offenen", ...]
```

---

## API Usage

### 1. Search Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/smart-search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Mueller Rechnung",
    "limit": 20
  }'
```

### 2. Autocomplete

```bash
curl -X GET "http://localhost:8000/api/v1/smart-search/autocomplete?q=Zeige&limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Health Check

```bash
curl http://localhost:8000/api/v1/smart-search/health
```

---

## Frontend Integration (React/TypeScript)

### Basic Search

```typescript
import { useState } from 'react';
import { api } from '@/lib/api';

function SmartSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);

  const handleSearch = async () => {
    const response = await api.post('/api/v1/smart-search', {
      query,
      limit: 20,
      include_suggestions: true,
      include_facets: true,
    });
    setResults(response.data);
  };

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Suchen..."
      />
      <button onClick={handleSearch}>Suchen</button>

      {results && (
        <div>
          <p>Erkannt als: {results.detected_type}</p>
          <p>Confidence: {results.interpretation.confidence}</p>
          <p>Dokumente: {results.total_documents}</p>
          <p>Entities: {results.total_entities}</p>
        </div>
      )}
    </div>
  );
}
```

### With Autocomplete

```typescript
import { useDebounce } from '@/hooks/useDebounce';

function SmartSearchWithAutocomplete() {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery.length >= 3) {
      api.get('/api/v1/smart-search/autocomplete', {
        params: { q: debouncedQuery, limit: 5 }
      }).then(res => setSuggestions(res.data.suggestions));
    }
  }, [debouncedQuery]);

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {suggestions.length > 0 && (
        <ul>
          {suggestions.map((s, i) => (
            <li key={i} onClick={() => setQuery(s)}>{s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

---

## Auto-Detection Cheat Sheet

| Query | Detected | Why? |
|-------|----------|------|
| "Zeige alle Rechnungen" | NLQ | Fragewort "zeige" |
| "Wie hoch ist die Summe" | NLQ | Aggregation "summe" |
| "Welche Dokumente sind offen" | NLQ | Fragewort + Verb |
| "Mueller Rechnung 2025" | Keyword | Kurze Query, keine Muster |
| "invoice AND payment" | Keyword | Boolean-Operatoren |

**Override mit force_mode**: `"nlq"` oder `"keyword"`

---

## Response Structure

```typescript
interface SmartSearchResponse {
  query: string;
  detected_type: "nlq" | "keyword";
  interpretation: {
    detected_type: string;
    confidence: number;
    reasoning: string;
    nlq_intent?: string;
    entities_found: string[];
  };
  documents: Document[];
  total_documents: number;
  entities: Entity[];
  total_entities: number;
  natural_response?: string;  // Nur bei NLQ
  nlq_confidence?: number;    // Nur bei NLQ
  suggestions: string[];
  facets?: Facets;
  search_time_ms: number;
}
```

---

## Common Use Cases

### 1. Standard Keyword-Suche

```python
result = await service.search(
    db=db,
    query="Mueller",
    user_id=user.id,
)
# → Detected: keyword
# → Documents: FTS + Semantic Hybrid
# → Entities: Mueller GmbH
```

### 2. Natürlichsprachliche Frage

```python
result = await service.search(
    db=db,
    query="Zeige alle offenen Rechnungen",
    user_id=user.id,
)
# → Detected: nlq
# → Intent: search
# → Natural Response: "Ich habe X offene Rechnungen gefunden."
```

### 3. Aggregations-Frage

```python
result = await service.search(
    db=db,
    query="Wie hoch ist die Summe aller Rechnungen",
    user_id=user.id,
)
# → Detected: nlq
# → Intent: aggregate
# → Natural Response: "Die Gesamtsumme beträgt X EUR."
```

### 4. Suche mit Facets

```python
result = await service.search(
    db=db,
    query="Rechnung",
    user_id=user.id,
    include_facets=True,
)

# Verwende Facets für Refinement
print(result.facets.document_types)  # {"invoice": 5, "contract": 2}
print(result.facets.statuses)        # {"pending": 3, "completed": 2}
```

---

## Debugging

### Enable Debug Logging

```python
import structlog
logger = structlog.get_logger(__name__)

# In Service
logger.debug(
    "smart_search_detection",
    query=query,
    detected_type=detected_type,
    confidence=confidence,
)
```

### Check Auto-Detection

```python
from app.services.smart_search_service import SmartSearchService

service = SmartSearchService()

# Test Detection direkt
detected_type, confidence, reasoning = service._detect_query_type("Zeige alle Rechnungen")
print(f"Type: {detected_type}, Confidence: {confidence}, Reason: {reasoning}")
```

### Prometheus Metrics

```bash
# Check request counts
curl http://localhost:9090/api/v1/query?query=smart_search_requests_total

# Check latency
curl http://localhost:9090/api/v1/query?query=smart_search_duration_seconds
```

---

## Testing

### Unit Test

```python
import pytest
from app.services.smart_search_service import SmartSearchService

@pytest.mark.asyncio
async def test_my_search(mock_db):
    service = SmartSearchService()
    result = await service.search(
        db=mock_db,
        query="test",
        user_id=uuid4(),
    )
    assert result.detected_type in ["nlq", "keyword"]
```

### Run Tests

```bash
# All Smart Search tests
pytest tests/unit/services/test_smart_search_service.py -v

# Specific test
pytest tests/unit/services/test_smart_search_service.py::TestQueryTypeDetection::test_detect_nlq_question_word -v

# With coverage
pytest tests/unit/services/test_smart_search_service.py --cov=app.services.smart_search_service
```

---

## Performance Tips

1. **Use Caching**: Identical queries are cached (if enabled)
2. **Limit Results**: Default 20, max 100
3. **Skip Facets**: Set `include_facets=False` if not needed
4. **Skip Suggestions**: Set `include_suggestions=False`
5. **Force Mode**: Use `force_mode` to skip auto-detection overhead

---

## Troubleshooting

### Problem: Auto-Detection falsch

**Lösung**: Use `force_mode`
```python
result = await service.search(
    query="...",
    force_mode=DetectedQueryType.NLQ,  # or KEYWORD
)
```

### Problem: Keine Ergebnisse bei NLQ

**Lösung**: Check NLQ Service logs, verify entities exist
```python
# Test mit Keyword-Mode
result = await service.search(
    query="...",
    force_mode=DetectedQueryType.KEYWORD,
)
```

### Problem: Langsame Suche

**Check**:
- Document count (index performance)
- Entity count (search complexity)
- Enable query caching
- Use Prometheus metrics to identify bottleneck

---

## Configuration

```python
# app/core/config.py
HYBRID_FTS_WEIGHT = 0.5           # FTS weight in hybrid search
HYBRID_SEMANTIC_WEIGHT = 0.5      # Semantic weight
AUTONOMY_NLQ_ENABLED = True       # Enable NLQ
SEARCH_CACHE_ENABLED = True       # Enable search cache
SEARCH_CACHE_TTL = 300            # Cache TTL (seconds)
```

---

## Need Help?

- **Docs**: `docs/features/SMART_SEARCH.md`
- **Tests**: `tests/unit/services/test_smart_search_service.py`
- **Service**: `app/services/smart_search_service.py`
- **API**: `app/api/v1/smart_search.py`

---

**Happy Searching!** 🔍
