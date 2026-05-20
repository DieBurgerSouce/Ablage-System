# Business Rules Engine & AI Generator

Vision 2.0 - Phase 2 (Januar 2026)

## Übersicht

Das Rules-Modul bietet:

1. **Business Rules Engine** - Regelbasierte Verarbeitung von Dokumenten
2. **AI Rule Generator** - KI-basierte Regel-Generierung aus natürlicher Sprache

## Module

### business_rules_engine.py

Regelbasierte Verarbeitung mit:
- Bedingungsauswertung (einfach & komplex)
- Aktionsausführung
- Regel-Priorisierung
- RuleSet-Verwaltung

**Verwendung:**
```python
from app.services.rules import BusinessRulesEngine

engine = BusinessRulesEngine(db)
result = await engine.evaluate_for_document(
    document_id=doc_id,
    rules=rules,
    dry_run=True,
)
```

### ai_rule_generator_service.py

KI-basierte Regelgenerierung mit Ollama (lokaler LLM):
- Natürlichsprachliche Prompts → strukturierte Regeln
- Confidence-Bewertung
- Deutsche Sprache optimiert
- On-premises (keine Cloud)

**Verwendung:**
```python
from app.services.rules import get_ai_rule_generator_service

service = await get_ai_rule_generator_service()
generated = await service.generate_rule(
    "Rechnungen über 10000 EUR müssen vom CFO genehmigt werden"
)
```

## API Endpoints

### Rules CRUD

- `GET /api/v1/rules` - Liste aller Regeln
- `POST /api/v1/rules` - Neue Regel erstellen
- `GET /api/v1/rules/{id}` - Regel abrufen
- `PATCH /api/v1/rules/{id}` - Regel aktualisieren
- `DELETE /api/v1/rules/{id}` - Regel löschen

### Testing & Evaluation

- `POST /api/v1/rules/test` - Regel testen (dry-run)
- `POST /api/v1/rules/evaluate/{document_id}` - Regel für Dokument auswerten
- `GET /api/v1/rules/evaluate/{document_id}/preview` - Preview ohne Ausführung

### AI Generation

- `POST /api/v1/rules/generate` - Regel aus Prompt generieren

### Schema/Info

- `GET /api/v1/rules/schema/operators` - Verfügbare Operatoren/Aktionen

## Datenmodell

### BusinessRule

```python
class BusinessRule:
    id: UUID
    name: str
    description: Optional[str]
    condition: Dict[str, Any]  # JSON-Bedingung
    actions: List[RuleAction]
    else_actions: Optional[List[RuleAction]]
    priority: RulePriority  # CRITICAL(100) bis LOW(10)
    category: RuleCategory  # approval, compliance, fraud, etc.
    is_active: bool
    stop_on_match: bool
```

### RuleCondition

Einfache Bedingung:
```python
{
    "field": "amount",
    "op": ">=",
    "value": 10000
}
```

Komplexe Bedingung (AND/OR):
```python
{
    "and": [
        {"field": "document_type", "op": "==", "value": "invoice"},
        {
            "or": [
                {"field": "amount", "op": ">=", "value": 10000},
                {"field": "supplier.is_new", "op": "==", "value": true}
            ]
        }
    ]
}
```

### RuleAction

```python
class RuleAction:
    type: ActionType  # require_approval, notify_admin, etc.
    params: Dict[str, Any]  # Aktionsspezifische Parameter
```

## Operatoren

| Kategorie | Operatoren |
|-----------|-----------|
| Vergleich | `==`, `!=`, `>`, `>=`, `<`, `<=` |
| String | `contains`, `not_contains`, `starts_with`, `ends_with`, `matches` |
| Liste | `in`, `not_in`, `is_empty`, `is_not_empty` |
| Null | `is_null`, `is_not_null` |
| Datum | `before`, `after`, `between`, `in_period` |
| Tags | `has_tag`, `has_any_tag`, `has_all_tags` |

## Aktionstypen

| Kategorie | Aktionen |
|-----------|----------|
| Genehmigung | `require_approval`, `require_cfo_approval`, `require_manager_approval` |
| Benachrichtigung | `notify_user`, `notify_team`, `notify_admin`, `send_email`, `send_slack` |
| Status | `set_status`, `set_priority`, `set_flag`, `remove_flag` |
| Workflow | `start_workflow`, `assign_to_user`, `assign_to_team` |
| Tags | `add_tag`, `remove_tag` |
| Prüfung | `flag_for_review`, `manual_review_required`, `block_processing` |

## Kategorien

- `approval` - Genehmigungsregeln
- `compliance` - Compliance-Regeln
- `fraud` - Betrugserkennungs-Regeln
- `workflow` - Workflow-Regeln
- `notification` - Benachrichtigungs-Regeln
- `data_quality` - Datenqualitäts-Regeln
- `custom` - Benutzerdefiniert

## AI Rule Generator Details

### System Prompt

Der AI Generator verwendet einen umfassenden System-Prompt mit:
- Verfügbaren Feldern (amount, document_type, supplier.*, etc.)
- Operatoren mit Beschreibungen
- Aktionstypen mit Parametern
- Kategorien
- Beispiele

### Confidence

Der LLM gibt eine Confidence-Bewertung (0.0-1.0):
- `>= 0.9`: Sehr sicher
- `0.8 - 0.9`: Gut
- `0.7 - 0.8`: Überprüfen
- `< 0.7`: Anpassen

### Explanation

Jede generierte Regel enthält eine Erklärung warum diese Regel sinnvoll ist.

### JSON Extraction

Robuste Extraktion aus LLM-Antworten:
1. Direktes JSON-Parsing
2. JSON aus Markdown-Block (```json ... ```)
3. Suche nach erstem `{` bis letztem `}`
4. Multi-Line Regex-Matching

## Beispiele

Siehe `docs/examples/ai_rule_generator_examples.md` für:
- Vollständige API-Beispiele
- Curl-Commands
- JavaScript/TypeScript Code
- Python Code
- Best Practices

## Tests

```bash
# Unit Tests
pytest tests/unit/services/rules/test_ai_rule_generator_service.py -v

# Integration Tests (erfordert Ollama)
pytest tests/integration/test_ai_rule_generator.py -v
```

## Voraussetzungen

### Ollama (für AI Generator)

```bash
# Docker
docker-compose up -d ollama

# Lokal
ollama serve
ollama pull mistral
```

### Environment Variables

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

## Deployment

1. Ollama muss verfügbar sein
2. Model muss gepullt sein (`mistral` empfohlen)
3. Keine weiteren Abhängigkeiten

## Performance

- **Regel-Evaluation**: <50ms für einfache Regeln
- **AI-Generierung**: 2-5s (abhängig von LLM-Model)
- **Batch-Evaluation**: <100ms für 10 Regeln

## Sicherheit

1. **Input-Validierung**: Alle Prompts werden validiert (5-1000 Zeichen)
2. **No Code Execution**: Regeln sind deklarativ, kein Python-Code
3. **Multi-Tenant**: Company-Isolation über RLS
4. **Audit-Logging**: Alle Regelausführungen werden protokolliert

## Logging

```python
import logging

logger = logging.getLogger("app.services.rules.ai_rule_generator_service")
logger.setLevel(logging.INFO)
```

Log-Level:
- `INFO`: Erfolgreiche Generierung
- `DEBUG`: Ollama-Responses
- `ERROR`: Fehler bei Generierung/Extraktion
- `WARNING`: Ollama nicht verfügbar

## Troubleshooting

### Ollama nicht erreichbar

**Symptom:** `Ollama nicht verfügbar`

**Lösung:**
```bash
docker-compose restart ollama
# oder
ollama serve
```

### Ungültiges JSON

**Symptom:** `Konnte kein gueltiges JSON extrahieren`

**Ursache:** LLM gibt kein strukturiertes JSON zurück

**Lösung:**
- Prompt umformulieren
- Anderes Model verwenden
- Temperature senken (0.1-0.3)

### Niedrige Confidence

**Symptom:** `confidence < 0.7`

**Ursache:** Prompt zu vage oder unbekannte Konzepte

**Lösung:**
- Präziseren Prompt verwenden
- Bekannte Felder/Operatoren nutzen
- Komplexität reduzieren

## Migration von manuellen Regeln

Bestehende Regeln können per AI Generator modernisiert werden:

```python
# Alt (manuell erstellt)
old_rule = {
    "name": "High Invoice Approval",
    "condition": {"field": "amount", "op": ">=", "value": 10000},
    "actions": [{"type": "require_approval"}]
}

# Neu (AI-generiert mit besserer Beschreibung)
generated = await service.generate_rule(
    "Rechnungen über 10000 EUR zur CFO-Genehmigung mit hoher Priorität"
)
# → Detailliertere Regel mit explanation und optimierten Aktionen
```

## Erweiterung

### Neue Felder hinzufügen

1. Feld im System-Prompt dokumentieren
2. In `VERFUEGBARE FELDER` Liste aufnehmen
3. Beispiele mit neuem Feld hinzufügen

### Neue Aktionen hinzufügen

1. `ActionType` Enum erweitern
2. Im System-Prompt dokumentieren
3. Implementierung in Business Rules Engine

### Neue Operatoren

1. `ConditionOperator` Enum erweitern
2. Im System-Prompt dokumentieren
3. Implementierung in Evaluator

## Roadmap

- [ ] Fine-tuning des LLM auf Ablage-System-spezifische Regeln
- [ ] Multi-Sprach-Support (EN/DE)
- [ ] Regel-Templates aus häufigen Generierungen
- [ ] A/B Testing von generierten Regeln
- [ ] Feedback-Loop: User-Korrekturen → LLM-Verbesserung
