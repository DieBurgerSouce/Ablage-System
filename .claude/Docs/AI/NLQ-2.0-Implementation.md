# Natural Language Query 2.0 - Implementation Guide

**Status**: ✅ Backend Complete
**Created**: 2026-01-28
**Type**: AI Feature

---

## Overview

Natural Language Query (NLQ) 2.0 erweitert das Ablage-System mit LLM-basierter SQL-Generierung. Benutzer können Datenbankabfragen in natürlicher deutscher Sprache stellen.

**Key Features**:
- LLM-basierte SQL-Generierung (Ollama + Qwen3:8b)
- Multi-Layer Security (SQL Injection Prevention)
- Intelligente Visualisierungs-Empfehlungen
- Redis-basiertes Caching
- On-Premises (keine Cloud-Abhängigkeiten)

---

## Architecture

```
User Query (German)
    ↓
NLQOrchestrator
    ↓
QueryCache ────→ [Cache Hit] ────→ Return Results
    ↓ [Cache Miss]
SchemaIntrospector
    ↓ (Schema Context)
SQLGenerator (Ollama)
    ↓ (Generated SQL)
SQLSanitizer ⚠️ SECURITY CRITICAL
    ↓ (Sanitized SQL)
PostgreSQL Execution
    ↓ (Raw Results)
ResultFormatter
    ↓
VisualizationRecommender
    ↓
NLQResponse + Cache
```

---

## File Structure

```
app/services/ai/nlq/
├── __init__.py                    # Module exports
├── nlq_orchestrator.py            # Main orchestrator
├── sql_sanitizer.py               # ⚠️ SECURITY: SQL injection prevention
├── sql_generator.py               # LLM-based SQL generation
├── schema_introspector.py         # DB schema context provider
├── result_formatter.py            # Result formatting for display
├── visualization_recommender.py   # Chart type recommendation
└── query_cache.py                 # Redis caching layer
```

---

## Core Components

### 1. NLQOrchestrator

**File**: `app/services/ai/nlq/nlq_orchestrator.py`

Hauptorchestrator für den gesamten NLQ-Workflow.

**Key Methods**:
```python
async def query(
    natural_query: str,
    user_id: UUID,
    company_id: UUID,
    db: AsyncSession
) -> NLQResponse

async def get_suggestions(
    company_id: UUID,
    db: AsyncSession,
    limit: int = 10
) -> List[str]

async def submit_feedback(
    query_log_id: UUID,
    rating: int,
    comment: Optional[str],
    db: AsyncSession
) -> None

async def health_check() -> Dict[str, Any]
```

**Workflow**:
1. Cache-Check
2. SQL-Generierung via LLM
3. SQL-Sanitization (Security)
4. Query-Ausführung mit Timeout
5. Result-Formatierung
6. Visualisierungs-Empfehlung
7. Logging
8. Caching

---

### 2. SQLSanitizer ⚠️ SECURITY CRITICAL

**File**: `app/services/ai/nlq/sql_sanitizer.py`

Letzte Verteidigungslinie gegen SQL-Injection bei LLM-generierten Queries.

**Security Features**:
- ✅ SELECT-only enforcement
- ✅ Table whitelist (25 allowed tables)
- ✅ PII column blacklist (12 forbidden columns)
- ✅ SQL injection pattern detection (8 patterns)
- ✅ Automatic company_id injection (multi-tenant isolation)
- ✅ Result row limit (max 1000)

**Allowed Tables**:
```python
ALLOWED_TABLES = {
    "documents", "business_entities", "invoice_tracking",
    "document_chains", "alerts", "smart_inbox_items",
    "zero_touch_results", "folders", "tags", "document_tags",
    "companies", "users", "approval_requests", "document_versions",
    "shipping_tracking", "contracts", "bank_transactions",
    "cash_entries", "expenses", "nlq_query_logs",
}
```

**PII Columns (Blacklist)**:
```python
PII_COLUMNS = {
    "password_hash", "totp_secret", "backup_codes", "refresh_token",
    "iban", "bic", "vat_id", "tax_id", "ssn",
    "api_key", "api_secret", "webhook_secret",
    "email_password", "imap_password",
}
```

**Forbidden SQL Patterns**:
```python
FORBIDDEN_PATTERNS = [
    r'\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b',
    r'\b(EXEC|EXECUTE|CALL)\b',
    r'--',  # SQL comments
    r'/\*',  # Block comments
    r';\s*\w',  # Multiple statements
    r'\bINTO\s+OUTFILE\b',
    r'\bLOAD\s+DATA\b',
    r'\bINTO\s+DUMPFILE\b',
]
```

**Example Usage**:
```python
sanitizer = SQLSanitizer()
result = sanitizer.sanitize(llm_generated_sql, company_id)

if result.safe:
    # Execute result.sanitized_sql
else:
    # Log result.violations
```

---

### 3. SQLGenerator

**File**: `app/services/ai/nlq/sql_generator.py`

LLM-basierte SQL-Generierung mit Ollama.

**Configuration**:
- **Ollama URL**: `http://localhost:11434`
- **Model**: `qwen3:8b` (optimal für SQL)
- **Timeout**: 30 Sekunden
- **Temperature**: 0.1 (deterministisch)

**Prompt Template**:
```
Du bist ein SQL-Experte für PostgreSQL. Generiere eine SQL-Abfrage basierend auf der natürlichen Sprache-Anfrage.

{schema_context}

## Anforderungen:
- Nur SELECT-Abfragen
- PostgreSQL-Syntax verwenden
- Deutsche Spaltennamen und Werte beachten
- Effiziente JOINs verwenden
- Aggregationen mit GROUP BY
- KEINE LIMIT-Klausel (wird automatisch hinzugefügt)
- KEINE WHERE-Klausel für company_id (wird automatisch injiziert)

## Natürliche Sprache-Anfrage:
{query}
```

**Confidence Estimation**:
- Base: 0.5
- +0.2: SELECT vorhanden
- +0.1: FROM vorhanden
- +0.05: JOIN, GROUP BY, ORDER BY
- -0.3: SQL zu kurz (<20 Zeichen)
- Max: 0.95 (nie 100% mit LLM)

---

### 4. SchemaIntrospector

**File**: `app/services/ai/nlq/schema_introspector.py`

Stellt DB-Schema-Kontext für LLM bereit.

**Output Format**:
```markdown
# Datenbank-Schema für SQL-Generierung

## Verfügbare Tabellen:

### documents
**Spalten:**
- `id`: UUID (PK)
- `filename`: VARCHAR
- `status`: VARCHAR
- `created_at`: TIMESTAMP
- `metadata`: JSONB

**Typische Abfragen:**
- Dokumente nach Status filtern
- Anzahl Dokumente pro Monat
- Dokumente mit hoher OCR-Confidence

## Wichtige Beziehungen:
- `documents.folder_id` → `folders.id`
- `documents.entity_id` → `business_entities.id`
```

**Features**:
- Schema-Caching für Performance
- PII-Spalten werden ausgeschlossen
- Nutzungsbeispiele pro Tabelle
- Relationship-Beschreibungen

---

### 5. ResultFormatter

**File**: `app/services/ai/nlq/result_formatter.py`

Formatiert Query-Ergebnisse für User-friendly Display.

**Output**:
```python
@dataclass
class FormattedResult:
    text_summary: str  # "42 Ergebnisse gefunden | Top: name = ABC GmbH"
    data: List[Dict[str, Any]]  # JSON-serializable
    visualization_type: str  # bar, line, pie, table, kpi
    visualization_config: Dict[str, Any]
    total_rows: int
```

**Visualization Configs**:

**KPI**:
```json
{
    "type": "kpi",
    "value": 42,
    "label": "Anzahl Dokumente",
    "format": "number"  // number, currency, decimal, compact
}
```

**Bar Chart**:
```json
{
    "type": "bar",
    "xAxis": "category",
    "yAxis": ["count"],
    "orientation": "vertical"  // vertical, horizontal
}
```

**Line Chart**:
```json
{
    "type": "line",
    "xAxis": "date",
    "yAxis": ["amount"],
    "smooth": true
}
```

**Pie Chart**:
```json
{
    "type": "pie",
    "labelColumn": "category",
    "valueColumn": "count",
    "showPercentage": true
}
```

**Table**:
```json
{
    "type": "table",
    "columns": [
        {"name": "amount", "type": "currency"},
        {"name": "date", "type": "date"}
    ],
    "sortable": true,
    "filterable": true
}
```

---

### 6. VisualizationRecommender

**File**: `app/services/ai/nlq/visualization_recommender.py`

Empfiehlt optimalen Chart-Typ basierend auf Query und Daten.

**Heuristics**:

| Bedingung | Chart Type | Beispiel |
|-----------|------------|----------|
| 1 Zeile, 1 Spalte | KPI | "Wie viele Dokumente?" |
| Aggregation (Summe, Durchschnitt) | KPI | "Gesamtumsatz?" |
| Zeit-Spalte + Query-Keywords | Line | "Umsatz-Entwicklung" |
| Prozent/Anteil in Query | Pie | "Verteilung nach Status" |
| 2-20 Zeilen, Kategorie-Spalte | Bar | "Top 10 Kunden" |
| >50 Zeilen oder >5 Spalten | Table | "Alle Rechnungen" |
| Default | Bar | Fallback |

**Time Series Detection**:
- Keywords: "trend", "verlauf", "entwicklung", "monat", "jahr"
- Spalten: "date", "datum", "time", "month", "created_at"

**Proportion Detection**:
- Keywords: "anteil", "prozent", "verteilung", "aufteilung"
- Spalten: "percent", "prozent"

---

### 7. QueryCache

**File**: `app/services/ai/nlq/query_cache.py`

Redis-basiertes Caching für schnelle Wiederholungs-Queries.

**Configuration**:
- **Key Prefix**: `nlq:cache:`
- **Default TTL**: 300 Sekunden (5 Minuten)
- **Hash**: SHA256(normalized_query + company_id)

**Key Methods**:
```python
async def get_cached(
    natural_query: str,
    company_id: str
) -> Optional[CachedResult]

async def set_cached(
    natural_query: str,
    company_id: str,
    generated_sql: str,
    columns: List[str],
    rows: List[tuple],
    visualization_type: str,
    text_summary: str,
    confidence: float,
    ttl: int = 300
) -> None

async def invalidate_all(company_id: str) -> int

async def get_cache_stats() -> Dict[str, Any]
```

**Multi-Tenant Isolation**:
- Cache-Key enthält company_id
- Gleiche Query für verschiedene Companies = verschiedene Caches

---

## API Integration

### Endpoints (noch zu erstellen)

```python
# app/api/v1/nlq.py

@router.post("/nlq/query")
async def execute_nlq_query(
    request: NLQQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis)
) -> NLQResponse

@router.get("/nlq/suggestions")
async def get_nlq_suggestions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[str]

@router.post("/nlq/feedback/{query_log_id}")
async def submit_nlq_feedback(
    query_log_id: UUID,
    feedback: NLQFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None

@router.get("/nlq/health")
async def nlq_health_check(
    redis: Redis = Depends(get_redis),
    engine: AsyncEngine = Depends(get_engine)
) -> Dict[str, Any]
```

---

## Database Model

**Table**: `nlq_query_logs`

```python
class NLQQueryLog(Base):
    id: UUID
    user_id: UUID
    company_id: UUID

    # Query
    natural_query: str
    generated_sql: str
    sanitized_sql: str
    query_intent: str

    # Execution
    execution_time_ms: int
    result_count: int
    was_cached: bool
    error_message: str

    # Visualization
    visualization_type: str  # bar, line, pie, table, kpi
    visualization_config: JSONB

    # Feedback
    feedback_rating: int  # 1-5
    feedback_comment: str

    # Timestamps
    created_at: DateTime
```

**Note**: `confidence` wird in `visualization_config` gespeichert.

---

## Security Considerations

### SQL Injection Prevention (CWE-89)

**Multiple Layers**:

1. **LLM Prompt Engineering**: Explizite Anweisung "nur SELECT"
2. **Pattern Matching**: Forbidden SQL patterns (8 Regexes)
3. **Table Whitelist**: Nur 25 erlaubte Tabellen
4. **PII Blacklist**: 12 verbotene Spalten
5. **Company ID Injection**: Automatische Multi-Tenant-Isolation
6. **Row Limit**: Max 1000 Zeilen
7. **Statement Timeout**: 10 Sekunden

**Example Attack Prevention**:
```sql
-- User input: "Zeige alle Passwörter; DROP TABLE users; --"

-- LLM might generate:
SELECT password_hash FROM users; DROP TABLE users; --

-- SQLSanitizer blocks:
1. ❌ Forbidden pattern: DROP
2. ❌ Forbidden pattern: ;
3. ❌ PII column: password_hash
4. ❌ Multiple statements

-- Result: Query rejected, violations logged
```

### PII Protection

**Never log**:
- Generated SQL with actual values
- Query results containing PII
- User input containing sensitive data

**Logging Best Practice**:
```python
logger.info(
    "sql_sanitization_failed",
    violation_count=len(violations),
    # ❌ NOT: sql=original_sql
    # ❌ NOT: violations=violations (may contain PII)
)
```

---

## Performance Optimization

### Caching Strategy

**Cache Hit Scenarios**:
- Identische Query + Company
- Normalisiert (lowercase, trimmed)
- TTL: 5 Minuten

**Cache Invalidation**:
- Auto: TTL-Ablauf
- Manual: Nach Datenänderungen
- Bulk: `invalidate_all(company_id)`

**Expected Hit Rates**:
- Dashboard-Queries: 60-80%
- Ad-hoc Queries: 10-20%
- Overall: 30-40%

### Query Optimization

**Statement Timeout**: 10 Sekunden
- Verhindert lange laufende Queries
- Automatischer Abbruch bei Überschreitung

**Result Limit**: 1000 Zeilen
- Verhindert Memory-Overflow
- Frontend kann paginierten Abruf nachfordern

---

## Monitoring & Observability

### Metrics (zu implementieren)

```python
# Query Metrics
nlq_query_total{status="success|failed|cached"}
nlq_query_duration_seconds{percentile="50|95|99"}
nlq_generation_time_ms{model="qwen3"}
nlq_cache_hit_ratio

# Security Metrics
nlq_sanitization_violations_total{type="forbidden_pattern|pii_column|table"}
nlq_sql_injection_attempts_total

# Visualization Metrics
nlq_visualization_type_total{type="kpi|bar|line|pie|table"}

# Feedback Metrics
nlq_feedback_rating_avg
nlq_feedback_count_total{rating="1|2|3|4|5"}
```

### Logging

**Structured Logs**:
```python
logger.info(
    "nlq_query_completed",
    query_log_id=str(query_log_id),
    execution_time_ms=execution_time_ms,
    result_count=len(rows),
    was_cached=False,
    visualization_type="bar"
)
```

**Never Log**:
- PII (customer names, IBANs, VAT-IDs)
- Full SQL with sensitive values
- User feedback verbatim (may contain PII)

---

## Testing Strategy

### Unit Tests

```python
# test_sql_sanitizer.py
async def test_sanitizer_blocks_drop():
    sanitizer = SQLSanitizer()
    result = sanitizer.sanitize("SELECT * FROM users; DROP TABLE users", company_id)
    assert not result.safe
    assert "DROP" in str(result.violations)

async def test_sanitizer_injects_company_id():
    sanitizer = SQLSanitizer()
    result = sanitizer.sanitize("SELECT * FROM documents", company_id)
    assert result.safe
    assert f"company_id = '{company_id}'" in result.sanitized_sql

# test_visualization_recommender.py
def test_recommender_kpi_single_value():
    recommender = VisualizationRecommender()
    viz_type = recommender.recommend("Anzahl Dokumente", ["count"], row_count=1)
    assert viz_type == "kpi"

def test_recommender_line_time_series():
    recommender = VisualizationRecommender()
    viz_type = recommender.recommend(
        "Umsatz-Entwicklung", ["month", "revenue"], row_count=12
    )
    assert viz_type == "line"
```

### Integration Tests

```python
# test_nlq_orchestrator.py
async def test_nlq_full_workflow(db: AsyncSession, redis: Redis):
    orchestrator = NLQOrchestrator(engine, redis)

    response = await orchestrator.query(
        natural_query="Wie viele Dokumente wurden heute hochgeladen?",
        user_id=test_user.id,
        company_id=test_company.id,
        db=db
    )

    assert response.confidence > 0.5
    assert response.result.total_rows >= 0
    assert response.visualization_type == "kpi"
    assert not response.was_cached

# test_cache_behavior.py
async def test_cache_hit_on_repeat_query(redis: Redis):
    cache = QueryCache(redis)
    query = "Anzahl Dokumente"

    # First call - miss
    result1 = await cache.get_cached(query, company_id)
    assert result1 is None

    # Store
    await cache.set_cached(query, company_id, sql, columns, rows, viz, summary, 0.9)

    # Second call - hit
    result2 = await cache.get_cached(query, company_id)
    assert result2 is not None
    assert result2.natural_query == query
```

### Security Tests

```python
# test_sql_injection.py
@pytest.mark.parametrize("malicious_input", [
    "'; DROP TABLE users; --",
    "UNION SELECT password_hash FROM users",
    "SELECT * FROM users WHERE id = 1; DELETE FROM documents",
    "/**/DROP/**/TABLE/**/users",
])
async def test_sql_injection_blocked(malicious_input):
    sanitizer = SQLSanitizer()
    result = sanitizer.sanitize(malicious_input, company_id)
    assert not result.safe
```

---

## Deployment Checklist

### Prerequisites

- [ ] Ollama installiert und gestartet
- [ ] Qwen3:8b Model geladen (`ollama pull qwen3:8b`)
- [ ] Redis verfügbar
- [ ] PostgreSQL 16+ mit pgvector

### Configuration

```bash
# .env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
REDIS_URL=redis://localhost:6380/0
NLQ_CACHE_TTL=300
NLQ_QUERY_TIMEOUT=10
```

### Health Checks

```bash
# Ollama
curl http://localhost:11434/api/tags

# Redis
redis-cli -p 6380 PING

# NLQ Service
curl http://localhost:8000/api/v1/nlq/health
```

---

## Example Queries

### KPI Queries

```
"Wie viele Dokumente wurden heute hochgeladen?"
"Gesamtanzahl Kunden"
"Durchschnittlicher Rechnungsbetrag"
```

### Bar Chart Queries

```
"Top 10 Kunden nach Umsatz"
"Dokumente pro Status"
"Rechnungen nach Mahnstufe"
```

### Line Chart Queries

```
"Umsatz-Entwicklung der letzten 12 Monate"
"Anzahl Dokumente pro Monat"
"Zahlungseingänge Trend"
```

### Pie Chart Queries

```
"Verteilung Dokumente nach Typ"
"Anteil überfälliger Rechnungen"
"Aufteilung Ausgaben nach Kategorie"
```

### Table Queries

```
"Alle offenen Rechnungen"
"Dokumente ohne OCR"
"Letzte 50 Uploads"
```

---

## Troubleshooting

### Ollama nicht erreichbar

**Symptom**: `RuntimeError: Ollama ist nicht verfügbar`

**Solution**:
```bash
# Ollama starten
ollama serve

# Model prüfen
ollama list
ollama pull qwen3:8b
```

### SQL-Generierung liefert schlechte Ergebnisse

**Symptom**: Confidence < 0.5, falsche SQL

**Solution**:
1. Schema-Cache invalidieren: `introspector.invalidate_cache()`
2. Prompt-Engineering verbessern
3. Model wechseln (z.B. `llama3:8b`)
4. Temperature anpassen (0.0 für deterministischer)

### Cache-Probleme

**Symptom**: Veraltete Ergebnisse

**Solution**:
```python
# Cache invalidieren
await cache.invalidate_all(company_id)

# TTL reduzieren
await cache.set_cached(..., ttl=60)  # 1 Minute
```

### Performance-Probleme

**Symptom**: Queries >10 Sekunden

**Solution**:
1. DB-Indizes prüfen
2. Query-Timeout reduzieren
3. Result-Limit reduzieren
4. Ollama-GPU aktivieren

---

## Future Enhancements

### Phase 2 (Q2 2026)

- [ ] **Query Suggestions**: Auto-Suggest basierend auf Context
- [ ] **Multi-Step Queries**: "Zeige Details für Top-Kunde" (follow-up)
- [ ] **Export Functions**: CSV/Excel-Export der Ergebnisse
- [ ] **Scheduled Queries**: Wiederkehrende Queries (täglich/wöchentlich)

### Phase 3 (Q3 2026)

- [ ] **Custom Dashboards**: User-defined NLQ-basierte Dashboards
- [ ] **Query Templates**: Vorgefertigte Queries pro Rolle
- [ ] **Multi-Language**: Englisch, Französisch
- [ ] **Voice Input**: Speech-to-NLQ

### Advanced Features

- [ ] **Query Optimizer**: LLM optimiert Query basierend auf Execution Plan
- [ ] **Schema Learning**: LLM lernt aus Feedback, verbessert SQL
- [ ] **Cross-Table Inference**: Automatische JOIN-Erkennung
- [ ] **Anomaly Detection**: "Zeige ungewöhnliche Transaktionen"

---

## Related Documentation

- **SQL Sanitizer**: `.claude/Docs/Security/SQL-Injection-Prevention.md` (to be created)
- **Ollama Setup**: `.claude/Docs/Operations/Runbooks/Ollama-Management.md` (to be created)
- **AI Services**: `.claude/Docs/AI/AI-Services-Overview.md` (to be created)

---

**Version**: 1.0
**Last Updated**: 2026-01-28
**Author**: Claude Sonnet 4.5
