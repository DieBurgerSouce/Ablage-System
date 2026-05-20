# AI Rule Generator Service

**Status**: Production-Ready (Januar 2026)
**Vision**: 2.0 - Phase 2
**Modul**: `app.services.rules.ai_rule_generator_service`

## Übersicht

Der AI Rule Generator verwendet Ollama (lokaler LLM) um aus natürlichsprachlichen Beschreibungen strukturierte Business Rules zu generieren.

## Kernfunktionalität

### Natürliche Sprache → Strukturierte Regel

**Eingabe (Prompt):**
```
Rechnungen über 10000 EUR müssen vom CFO genehmigt werden
```

**Ausgabe (Strukturierte Regel):**
```json
{
  "name": "Hohe Rechnungen CFO-Genehmigung",
  "description": "Rechnungen ab 10.000 EUR erfordern CFO-Freigabe",
  "category": "approval",
  "priority": 90,
  "condition": {
    "and": [
      {"field": "document_type", "op": "==", "value": "invoice"},
      {"field": "amount", "op": ">=", "value": 10000}
    ]
  },
  "actions": [
    {"type": "require_cfo_approval", "params": {}},
    {"type": "set_priority", "params": {"priority": 5}}
  ],
  "confidence": 0.95,
  "explanation": "Vier-Augen-Prinzip für hohe Beträge"
}
```

## API

### Endpoint

```
POST /api/v1/rules/generate
```

### Request

```json
{
  "prompt": "Natürlichsprachliche Beschreibung (5-1000 Zeichen)"
}
```

### Response

```json
{
  "name": "Regelname",
  "description": "Beschreibung",
  "code": null,
  "category": "approval|compliance|fraud|workflow|notification|data_quality|custom",
  "priority": 1-100,
  "condition": {...},
  "actions": [...],
  "else_actions": [...] | null,
  "confidence": 0.0-1.0,
  "explanation": "Warum diese Regel sinnvoll ist"
}
```

## Service-Verwendung

### Python

```python
from app.services.rules import get_ai_rule_generator_service

# Service abrufen
service = await get_ai_rule_generator_service()

# Regel generieren
generated = await service.generate_rule(
    "Neue Lieferanten zur manuellen Prüfung markieren"
)

print(f"Name: {generated.name}")
print(f"Confidence: {generated.confidence}")
print(f"Erklärung: {generated.explanation}")
```

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/rules/generate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Skonto-Fristen überwachen"}'
```

## Verfügbare Elemente

### Felder

| Feld | Typ | Beispiel |
|------|-----|----------|
| `amount` | Decimal | 10000.50 |
| `document_type` | String | invoice, contract |
| `supplier.name` | String | Müller GmbH |
| `supplier.is_new` | Boolean | true |
| `customer.name` | String | Schmidt AG |
| `due_date` | Date | 2026-02-15 |
| `status` | String | pending, approved |
| `tags` | List[String] | ["urgent", "high-value"] |
| `ocr_confidence` | Float | 0.95 |
| `has_skonto` | Boolean | true |
| `is_duplicate` | Boolean | false |

### Operatoren

| Operator | Verwendung |
|----------|------------|
| `==`, `!=` | Gleichheit |
| `>`, `>=`, `<`, `<=` | Vergleich |
| `contains`, `not_contains` | String-Suche |
| `starts_with`, `ends_with` | String-Muster |
| `in`, `not_in` | Listen-Zugehörigkeit |
| `is_empty`, `is_not_empty` | Leer-Prüfung |
| `before`, `after`, `between` | Datum-Vergleich |
| `has_tag`, `has_any_tag` | Tag-Prüfung |

### Aktionen

| Aktion | Beschreibung | Parameter |
|--------|--------------|-----------|
| `require_approval` | Genehmigung erforderlich | - |
| `require_cfo_approval` | CFO-Genehmigung | - |
| `flag_for_review` | Zur Prüfung | - |
| `notify_admin` | Admin benachrichtigen | - |
| `notify_user` | Benutzer benachrichtigen | `user_id` |
| `send_email` | E-Mail senden | `to`, `subject`, `body` |
| `add_tag` | Tag hinzufügen | `tag` |
| `set_status` | Status setzen | `status` |
| `set_priority` | Priorität setzen | `priority` (1-5) |
| `block_processing` | Verarbeitung blockieren | - |

### Kategorien

- `approval` - Genehmigungsregeln
- `compliance` - Compliance-Regeln
- `fraud` - Betrugserkennungs-Regeln
- `workflow` - Workflow-Regeln
- `notification` - Benachrichtigungs-Regeln
- `data_quality` - Datenqualitäts-Regeln
- `custom` - Benutzerdefiniert

## Beispiel-Prompts

### 1. Skonto-Überwachung

```
Erstelle Regel für Skonto-Überwachung
```

→ Generiert Regel mit `has_skonto` Bedingung und `notify_admin` Aktion

### 2. CFO-Genehmigung

```
Rechnungen über 10000 EUR müssen vom CFO genehmigt werden
```

→ Generiert Regel mit `amount >= 10000` und `require_cfo_approval`

### 3. Neue Lieferanten

```
Neue Lieferanten zur manuellen Prüfung markieren
```

→ Generiert Regel mit `supplier.is_new == true` und `flag_for_review`

### 4. Duplikat-Erkennung

```
Duplikate mit niedriger OCR-Konfidenz blockieren
```

→ Generiert Regel mit `is_duplicate == true AND ocr_confidence < 0.8` und `block_processing`

### 5. Fälligkeits-Warnung

```
Warnung bei Rechnungen die in 3 Tagen fällig werden
```

→ Generiert Regel mit `due_date between today+3d and today+4d` und `notify_admin`

## Confidence-Bewertung

| Confidence | Bedeutung | Aktion |
|------------|-----------|--------|
| ≥ 0.9 | Sehr sicher | Minimale Anpassung |
| 0.8 - 0.9 | Gut | Kleinere Anpassungen |
| 0.7 - 0.8 | Überprüfen | Größere Anpassungen |
| < 0.7 | Unsicher | Komplett überprüfen |

## Best Practices

### ✅ Gute Prompts

- Spezifisch: "Rechnungen über 10000 EUR zur CFO-Genehmigung"
- Mit Kontext: "Neue Lieferanten mit Rechnungen über 5000 EUR zur Prüfung"
- Aktionsorientiert: "Benachrichtige Admin bei niedriger OCR-Qualität"

### ❌ Schlechte Prompts

- Zu vage: "Genehmigung"
- Ohne Kontext: "Irgendwas mit Lieferanten"
- Unklar: "Mach was mit Rechnungen"

### Workflow

1. **Generieren**: Regel mit AI Generator erstellen
2. **Prüfen**: Bedingungen und Aktionen überprüfen
3. **Anpassen**: Ggf. Priority/Category anpassen
4. **Testen**: Mit `/api/v1/rules/test` testen
5. **Speichern**: Mit `/api/v1/rules` speichern

## Technische Details

### Ollama Integration

```python
class AIRuleGeneratorService:
    SYSTEM_PROMPT = """
    Du bist ein Experte für Geschäftsregeln...
    VERFÜGBARE FELDER:
    - amount, document_type, supplier.*, ...
    OPERATOREN:
    - ==, !=, >, >=, <, <=, contains, ...
    AKTIONEN:
    - require_approval, notify_admin, ...
    """

    async def generate_rule(self, prompt: str) -> GeneratedRule:
        response = await self.ollama.generate(
            prompt=f"Erstelle eine Geschäftsregel für: {prompt}",
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,  # Niedrig für konsistente Struktur
            format_json=True,
        )
        return GeneratedRule(**self._extract_json(response))
```

### JSON-Extraktion

Robuste Multi-Methoden-Extraktion:

1. **Direktes Parsing**: `json.loads(text)`
2. **Markdown-Block**: ` ```json ... ``` `
3. **Regex-Suche**: Erstes `{` bis letztes `}`
4. **Multi-Line**: `\{[\s\S]*\}` Pattern

### Error Handling

```python
try:
    generated = await service.generate_rule(prompt)
except ValueError as e:
    # Ungültiges JSON
    raise HTTPException(422, f"KI konnte keine gültige Regel generieren: {e}")
except Exception as e:
    # Ollama-Fehler
    raise HTTPException(500, f"Fehler bei der Regelgenerierung: {e}")
```

## Voraussetzungen

### Ollama

```bash
# Docker
docker-compose up -d ollama

# Lokal
ollama serve
ollama pull mistral
```

### Environment

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

## Testing

### Unit Tests

```bash
pytest tests/unit/services/rules/test_ai_rule_generator_service.py -v
```

### Integration Tests

```bash
# Erfordert laufenden Ollama-Server
pytest tests/integration/test_ai_rule_generator_api.py --run-integration -v
```

## Troubleshooting

### Ollama nicht erreichbar

**Fehler:**
```
Fehler bei der Regelgenerierung: Ollama nicht erreichbar
```

**Lösung:**
```bash
docker-compose restart ollama
# oder
ollama serve
```

### Ungültiges JSON

**Fehler:**
```
Konnte kein gültiges JSON aus Antwort extrahieren
```

**Ursachen:**
- LLM gibt Text statt JSON zurück
- Model überlastet
- Prompt zu komplex

**Lösungen:**
- Prompt vereinfachen
- Anderes Model verwenden (llama2, codellama)
- Temperature senken (0.1)

### Niedrige Confidence

**Ursachen:**
- Unbekannte Felder
- Widersprüchliche Bedingungen
- Zu komplexer Prompt

**Lösungen:**
- Bekannte Felder verwenden (siehe Tabelle)
- Prompt aufteilen
- Beispiel-Prompt als Vorlage

## Sicherheit

1. **Input-Validierung**: Prompt 5-1000 Zeichen
2. **No Code Execution**: Nur deklarative Regeln
3. **Multi-Tenant**: Company-Isolation
4. **Preview-Modus**: Regel wird NICHT automatisch gespeichert

## Performance

- **Generierung**: 2-5 Sekunden (abhängig von LLM)
- **Ollama-Latenz**: ~1-2 Sekunden
- **JSON-Extraktion**: <10ms
- **Validierung**: <5ms

## Logging

```python
logger.info(f"Generiere Regel aus Prompt: {prompt[:100]}...")
logger.debug(f"Ollama Response: {response[:200]}...")
logger.info(f"Regel erfolgreich generiert: {generated.name} (Confidence: {generated.confidence:.2f})")
logger.error(f"Fehler bei Regel-Generierung: {e}", exc_info=True)
```

## Roadmap

- [ ] Fine-tuning auf Ablage-System-Regeln
- [ ] Multi-Sprach-Support (EN/DE)
- [ ] Regel-Templates aus häufigen Generierungen
- [ ] A/B Testing generierter Regeln
- [ ] Feedback-Loop für LLM-Verbesserung

## Siehe auch

- **Beispiele**: `docs/examples/ai_rule_generator_examples.md`
- **README**: `app/services/rules/README.md`
- **Business Rules Engine**: `app/services/rules/business_rules_engine.py`
- **API Docs**: `/docs` → `/api/v1/rules/generate`
