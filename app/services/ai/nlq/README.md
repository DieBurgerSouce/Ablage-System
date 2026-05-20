# Natural Language Query 2.0 - Quick Reference

LLM-basierte SQL-Generierung für natürlichsprachige Datenbankabfragen.

## Quick Start

```python
from app.services.ai.nlq import NLQOrchestrator

# Initialize
orchestrator = NLQOrchestrator(engine, redis)

# Execute query
response = await orchestrator.query(
    natural_query="Wie viele Dokumente wurden heute hochgeladen?",
    user_id=user.id,
    company_id=user.company_id,
    db=db
)

# Access results
print(response.result.text_summary)  # "42 Dokumente gefunden"
print(response.visualization_type)    # "kpi"
print(response.confidence)            # 0.85
```

## Architecture

```
User Query → Cache → LLM → Sanitizer → DB → Formatter → Response
              ↓                          ↓
           Cache Hit                  Visualizer
```

## Core Components

| Component | Purpose |
|-----------|---------|
| `NLQOrchestrator` | Main workflow coordinator |
| `SQLSanitizer` | ⚠️ SECURITY: SQL injection prevention |
| `SQLGenerator` | LLM-based SQL generation (Ollama) |
| `SchemaIntrospector` | DB schema context provider |
| `ResultFormatter` | Format results for display |
| `VisualizationRecommender` | Recommend chart type |
| `QueryCache` | Redis caching layer |

## Security

**CRITICAL**: `SQLSanitizer` verhindert SQL-Injection:

```python
✅ SELECT-only enforcement
✅ Table whitelist (25 tables)
✅ PII column blacklist (12 columns)
✅ Pattern-based attack detection
✅ Automatic company_id injection
✅ Result row limit (1000)
```

**Never bypass sanitization!**

## Configuration

```bash
# .env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
NLQ_CACHE_TTL=300  # 5 minutes
NLQ_QUERY_TIMEOUT=10  # seconds
```

## Example Queries

```python
# KPI
"Wie viele Dokumente wurden heute hochgeladen?"
→ visualization_type: "kpi"

# Bar Chart
"Top 10 Kunden nach Umsatz"
→ visualization_type: "bar"

# Line Chart
"Umsatz-Entwicklung der letzten 12 Monate"
→ visualization_type: "line"

# Pie Chart
"Verteilung Dokumente nach Status"
→ visualization_type: "pie"

# Table
"Alle offenen Rechnungen"
→ visualization_type: "table"
```

## Health Check

```python
health = await orchestrator.health_check()
# {
#   "service": "nlq",
#   "status": "healthy",
#   "components": {
#     "ollama": {"status": "healthy", "model": "qwen3:8b"},
#     "redis": {"status": "healthy"},
#     "database": {"status": "healthy"}
#   }
# }
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Ollama nicht erreichbar | `ollama serve` |
| Model fehlt | `ollama pull qwen3:8b` |
| Cache-Probleme | `await cache.invalidate_all(company_id)` |
| Schlechte SQL | Schema-Cache invalidieren, Prompt verbessern |

## Testing

```bash
# Unit tests
pytest tests/unit/services/ai/nlq/ -v

# Integration tests
pytest tests/integration/test_nlq_orchestrator.py -v

# Security tests
pytest tests/security/test_sql_injection.py -v
```

## Documentation

Full documentation: `.claude/Docs/AI/NLQ-2.0-Implementation.md`
