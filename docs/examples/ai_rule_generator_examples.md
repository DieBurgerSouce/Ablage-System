# AI Rule Generator - Beispiele

Vision 2.0 - Phase 2 (Januar 2026)

## Überblick

Der AI Rule Generator verwendet Ollama (lokaler LLM) um aus natürlichsprachlichen Beschreibungen strukturierte Business Rules zu generieren.

## API Endpoint

```
POST /api/v1/rules/generate
```

**Request:**
```json
{
  "prompt": "Rechnungen über 10000 EUR müssen vom CFO genehmigt werden"
}
```

**Response:**
```json
{
  "name": "Hohe Rechnungen CFO-Genehmigung",
  "description": "Rechnungen ab 10.000 EUR erfordern CFO-Freigabe",
  "code": null,
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
  "else_actions": null,
  "confidence": 0.95,
  "explanation": "Vier-Augen-Prinzip für hohe Beträge"
}
```

## Beispiel-Prompts

### 1. Skonto-Überwachung

**Prompt:**
```
Erstelle Regel für Skonto-Überwachung
```

**Generierte Regel:**
```json
{
  "name": "Skonto-Frist Warnung",
  "description": "Benachrichtigt bei ablaufenden Skonto-Fristen",
  "category": "notification",
  "priority": 75,
  "condition": {
    "and": [
      {"field": "has_skonto", "op": "==", "value": true},
      {"field": "skonto_deadline", "op": "between", "value": ["today", "today+3d"]}
    ]
  },
  "actions": [
    {"type": "notify_admin", "params": {}},
    {"type": "add_tag", "params": {"tag": "skonto-ablauf"}}
  ],
  "confidence": 0.9,
  "explanation": "Warnt rechtzeitig vor Skonto-Ablauf (3 Tage Vorlauf)"
}
```

### 2. Neue Lieferanten

**Prompt:**
```
Neue Lieferanten zur manuellen Prüfung markieren
```

**Generierte Regel:**
```json
{
  "name": "Neue Lieferanten Review",
  "description": "Neue Lieferanten zur manuellen Prüfung",
  "category": "compliance",
  "priority": 80,
  "condition": {
    "field": "supplier.is_new",
    "op": "==",
    "value": true
  },
  "actions": [
    {"type": "flag_for_review", "params": {}},
    {"type": "add_tag", "params": {"tag": "neuer-lieferant"}},
    {"type": "notify_admin", "params": {}}
  ],
  "else_actions": [
    {"type": "add_tag", "params": {"tag": "bekannter-lieferant"}}
  ],
  "confidence": 0.88,
  "explanation": "KYC für neue Geschäftspartner"
}
```

### 3. Duplikat-Erkennung

**Prompt:**
```
Duplikate mit niedriger OCR-Konfidenz blockieren
```

**Generierte Regel:**
```json
{
  "name": "Duplikat-Blocker",
  "description": "Blockiert verdächtige Duplikate",
  "category": "fraud",
  "priority": 100,
  "condition": {
    "and": [
      {"field": "is_duplicate", "op": "==", "value": true},
      {
        "or": [
          {"field": "ocr_confidence", "op": "<", "value": 0.8},
          {"field": "supplier.is_new", "op": "==", "value": true}
        ]
      }
    ]
  },
  "actions": [
    {"type": "block_processing", "params": {}},
    {"type": "manual_review_required", "params": {}}
  ],
  "confidence": 0.92,
  "explanation": "Schutz vor Duplikat-Betrug mit niedriger OCR-Qualität"
}
```

### 4. Fälligkeits-Warnung

**Prompt:**
```
Warnung bei Rechnungen die in 3 Tagen fällig werden
```

**Generierte Regel:**
```json
{
  "name": "Fälligkeits-Reminder",
  "description": "Warnt 3 Tage vor Fälligkeit",
  "category": "notification",
  "priority": 70,
  "condition": {
    "and": [
      {"field": "document_type", "op": "==", "value": "invoice"},
      {"field": "due_date", "op": "between", "value": ["today+3d", "today+4d"]}
    ]
  },
  "actions": [
    {"type": "notify_admin", "params": {}},
    {"type": "add_tag", "params": {"tag": "bald-faellig"}},
    {"type": "set_priority", "params": {"priority": 4}}
  ],
  "confidence": 0.87,
  "explanation": "Rechtzeitige Zahlungserinnerung"
}
```

### 5. Qualitätsprüfung

**Prompt:**
```
Dokumente mit niedriger OCR-Qualität zur Überprüfung
```

**Generierte Regel:**
```json
{
  "name": "OCR-Qualität niedrig",
  "description": "Prüfung bei niedriger OCR-Konfidenz",
  "category": "data_quality",
  "priority": 60,
  "condition": {
    "field": "ocr_confidence",
    "op": "<",
    "value": 0.85
  },
  "actions": [
    {"type": "flag_for_review", "params": {}},
    {"type": "add_tag", "params": {"tag": "ocr-unsicher"}},
    {"type": "notify_team", "params": {"team_id": "quality-team"}}
  ],
  "confidence": 0.85,
  "explanation": "Sichert Datenqualität durch manuelle Prüfung"
}
```

## Verwendung im Code

### Python (Service)

```python
from app.services.rules.ai_rule_generator_service import get_ai_rule_generator_service

# Service abrufen
service = await get_ai_rule_generator_service()

# Regel generieren
generated = await service.generate_rule(
    "Rechnungen über 5000 EUR zur Manager-Genehmigung"
)

print(f"Name: {generated.name}")
print(f"Kategorie: {generated.category}")
print(f"Confidence: {generated.confidence}")
print(f"Erklärung: {generated.explanation}")

# Regel in DB speichern (optional)
# ... create_rule() API verwenden
```

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/rules/generate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Skonto-Fristen überwachen und warnen"
  }'
```

### JavaScript/TypeScript (Frontend)

```typescript
const generateRule = async (prompt: string) => {
  const response = await fetch('/api/v1/rules/generate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ prompt }),
  });

  const generated = await response.json();

  console.log('Generierte Regel:', generated.name);
  console.log('Confidence:', generated.confidence);
  console.log('Erklärung:', generated.explanation);

  return generated;
};

// Verwendung
const rule = await generateRule(
  "Neue Lieferanten zur Prüfung markieren"
);
```

## Verfügbare Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `amount` | Decimal | Rechnungsbetrag in EUR |
| `document_type` | String | invoice, contract, receipt, order, etc. |
| `supplier.name` | String | Lieferantenname |
| `supplier.is_new` | Boolean | Ist neuer Lieferant |
| `customer.name` | String | Kundenname |
| `due_date` | Date | Fälligkeitsdatum |
| `invoice_date` | Date | Rechnungsdatum |
| `created_at` | DateTime | Erstellungsdatum |
| `status` | String | pending, approved, rejected, processed |
| `tags` | List[String] | Tags |
| `ocr_confidence` | Float | OCR-Konfidenz (0.0-1.0) |
| `has_skonto` | Boolean | Hat Skonto-Bedingungen |
| `skonto_deadline` | Date | Skonto-Frist |
| `is_duplicate` | Boolean | Ist Duplikat |
| `payment_terms` | String | Zahlungsbedingungen |

## Verfügbare Operatoren

| Operator | Beschreibung |
|----------|--------------|
| `==` | Gleich |
| `!=` | Ungleich |
| `>` | Größer |
| `>=` | Größer-gleich |
| `<` | Kleiner |
| `<=` | Kleiner-gleich |
| `contains` | String enthält |
| `not_contains` | String enthält nicht |
| `starts_with` | String beginnt mit |
| `ends_with` | String endet mit |
| `matches` | Regex-Pattern |
| `in` | In Liste |
| `not_in` | Nicht in Liste |
| `is_empty` | Leer |
| `is_not_empty` | Nicht leer |
| `is_null` | Null |
| `is_not_null` | Nicht null |
| `before` | Datum vor |
| `after` | Datum nach |
| `between` | Zwischen |
| `has_tag` | Hat Tag |
| `has_any_tag` | Hat mindestens einen Tag |
| `has_all_tags` | Hat alle Tags |

## Verfügbare Aktionen

| Aktion | Parameter | Beschreibung |
|--------|-----------|--------------|
| `require_approval` | - | Genehmigung erforderlich |
| `require_cfo_approval` | - | CFO-Genehmigung |
| `require_manager_approval` | - | Manager-Genehmigung |
| `flag_for_review` | - | Zur Prüfung markieren |
| `manual_review_required` | - | Manuelle Prüfung |
| `notify_admin` | - | Admin benachrichtigen |
| `notify_user` | `user_id` | Benutzer benachrichtigen |
| `notify_team` | `team_id` | Team benachrichtigen |
| `send_email` | `to`, `subject`, `body` | E-Mail senden |
| `send_slack` | `channel`, `message` | Slack-Nachricht |
| `add_tag` | `tag` | Tag hinzufügen |
| `remove_tag` | `tag` | Tag entfernen |
| `set_status` | `status` | Status setzen |
| `set_priority` | `priority` | Priorität setzen (1-5) |
| `start_workflow` | `workflow_id` | Workflow starten |
| `assign_to_user` | `user_id` | Benutzer zuweisen |
| `block_processing` | - | Verarbeitung blockieren |

## Kategorien

- `approval` - Genehmigungsregeln
- `compliance` - Compliance-Regeln
- `fraud` - Betrugserkennungs-Regeln
- `workflow` - Workflow-Regeln
- `notification` - Benachrichtigungs-Regeln
- `data_quality` - Datenqualitäts-Regeln
- `custom` - Benutzerdefiniert

## Best Practices

### 1. Klare Prompts

✅ **Gut:**
```
Rechnungen über 10000 EUR müssen vom CFO genehmigt werden
```

❌ **Schlecht:**
```
Genehmigung
```

### 2. Spezifische Bedingungen

✅ **Gut:**
```
Neue Lieferanten mit Rechnungen über 5000 EUR zur Prüfung
```

❌ **Schlecht:**
```
Irgendwas mit Lieferanten
```

### 3. Nachbearbeitung

Die generierte Regel ist ein **Vorschlag**. Immer:
1. Bedingungen überprüfen
2. Aktionen anpassen
3. Priorität festlegen
4. Testen mit `/api/v1/rules/test`
5. Dann speichern mit `/api/v1/rules`

### 4. Confidence beachten

- `>= 0.9`: Sehr sicher, wenig Anpassung nötig
- `0.8 - 0.9`: Gut, ggf. kleinere Anpassungen
- `0.7 - 0.8`: Überprüfen, größere Anpassungen möglich
- `< 0.7`: Komplett überprüfen

## Troubleshooting

### Ollama nicht verfügbar

**Fehler:**
```
Fehler bei der Regelgenerierung: Ollama nicht erreichbar
```

**Lösung:**
```bash
# Ollama starten
docker-compose up -d ollama

# Oder lokal
ollama serve

# Model pullen (falls noch nicht vorhanden)
ollama pull mistral
```

### Ungültiges JSON

**Fehler:**
```
KI konnte keine gültige Regel generieren
```

**Lösung:**
- Prompt umformulieren (klarer/spezifischer)
- Anderes Model verwenden (z.B. llama2)
- Model neu laden

### Niedrige Confidence

**Ursache:**
- Prompt zu vage
- Unbekannte Felder/Operatoren
- Widersprüchliche Bedingungen

**Lösung:**
- Prompt präzisieren
- Bekannte Felder verwenden (siehe Tabelle oben)
- Komplexität reduzieren

## Hinweise

1. **Preview-Modus**: Die Regel wird NICHT automatisch gespeichert
2. **Manuelle Bearbeitung**: Immer die generierte Regel prüfen
3. **Testing**: Vor dem Speichern mit `/test` testen
4. **Lokaler LLM**: Keine Cloud-Abhängigkeiten, alles on-premises
5. **Deutsche Sprache**: Prompts auf Deutsch liefern beste Ergebnisse
