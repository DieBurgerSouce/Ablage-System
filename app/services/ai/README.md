# AI Services

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält alle KI-bezogenen Services für intelligente Dokumentenverarbeitung, Automatisierung und Entscheidungsunterstützung.

---

## Services

### Kernservices

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **FinanceAssistantService** | `finance_assistant_service.py` | KI-Finanzassistent mit NLQ |
| **NLQService** | `nlq_service.py` | Natural Language Query Parsing |
| **ActionExecutorService** | `action_executor_service.py` | Ausführung von KI-Aktionen |
| **InsightGeneratorService** | `insight_generator_service.py` | Proaktive Insights |
| **OllamaService** | `ollama_service.py` | Ollama LLM Integration |

### Kategorisierung & Matching

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **AutoCategorizationService** | `auto_categorization_service.py` | Automatische Dokumentkategorisierung |
| **SmartMatchingService** | `smart_matching_service.py` | Entity-zu-Dokument Matching |
| **DuplicateDetectionService** | `duplicate_detection_service.py` | Duplikaterkennung |

### Vorhersage & Analyse

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **PredictiveActionService** | `predictive_action_service.py` | Vorhersage nächster Aktionen |
| **AnomalyDetectionService** | `anomaly_detection_service.py` | Anomalieerkennung |
| **DecisionService** | `decision_service.py` | Entscheidungsunterstützung |
| **RoutingIntelligenceService** | `routing_intelligence_service.py` | Intelligentes OCR-Routing |

### Autonomie & Learning

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **AutonomousActionsService** | `autonomous_actions_service.py` | Autonome Aktionsausführung |
| **LearningPipeline** | `learning_pipeline.py` | ML Learning Pipeline |

### Hilfsfunktionen

| Modul | Datei | Beschreibung |
|-------|-------|--------------|
| **TextUtils** | `text_utils.py` | Textverarbeitung, Normalisierung |
| **ExtractedDataWrapper** | `extracted_data_wrapper.py` | OCR-Daten Wrapper |

---

## FinanceAssistantService

Der zentrale KI-Finanzassistent für natürlichsprachliche Interaktionen.

### Features

- Natural Language Query (NLQ) Verständnis
- Intent-Erkennung (search, execute, explain, suggest)
- Aktionsvorschläge mit Bestätigungsworkflow
- Konversationsgedächtnis
- Proaktive Insights

### Intents

| Intent | Beispiel | Aktion |
|--------|----------|--------|
| `search` | "Zeige alle Rechnungen von Müller" | Dokumentensuche |
| `execute_action` | "Genehmige die Rechnung" | Aktion ausführen |
| `explain` | "Warum ist der Risiko-Score hoch?" | Erklärung generieren |
| `suggest_booking` | "Wie soll ich das buchen?" | Buchungsvorschlag |
| `summarize` | "Fasse die Cashflow-Situation zusammen" | Zusammenfassung |
| `compare` | "Vergleiche Q1 mit Q2" | Vergleichsanalyse |

### Verwendung

```python
from app.services.ai.finance_assistant_service import FinanceAssistantService

service = FinanceAssistantService(db)
response = await service.process_query(
    query="Zeige alle unbezahlten Rechnungen über 1000€",
    user_id=user.id,
    company_id=company.id,
    context={"page": "invoices"}
)
```

---

## NLQService

Parst natürlichsprachliche Anfragen in strukturierte Queries.

### Features

- Deutsche Sprachverarbeitung
- Datumsextraktion ("letzte Woche", "Q1 2026")
- Betragsextraktion ("über 1000€", "zwischen 500 und 2000")
- Entity-Erkennung ("von Müller GmbH")
- Operator-Mapping ("unbezahlt" → status=open)

### Beispiel

```python
from app.services.ai.nlq_service import NLQService

nlq = NLQService()
parsed = await nlq.parse(
    "Alle unbezahlten Rechnungen von Müller über 500€ seit Januar"
)
# Result:
# {
#   "entity": "Müller",
#   "status": "open",
#   "amount_min": 500,
#   "date_from": "2026-01-01"
# }
```

---

## ActionExecutorService

Führt KI-vorgeschlagene Aktionen aus.

### Unterstützte Aktionen

| Aktion | Beschreibung | Bestätigung |
|--------|--------------|-------------|
| `approve_invoice` | Rechnung genehmigen | Erforderlich |
| `mark_paid` | Als bezahlt markieren | Erforderlich |
| `increase_dunning` | Mahnstufe erhöhen | Erforderlich |
| `create_booking` | Buchung erstellen | Erforderlich |
| `send_notification` | Benachrichtigung senden | Optional |
| `schedule_export` | Export planen | Optional |

### Bestätigungsworkflow

```
KI schlägt Aktion vor
       ↓
User bestätigt/ablehnt
       ↓
ActionExecutor führt aus
       ↓
Ergebnis wird protokolliert
```

---

## AutonomousActionsService

Ermöglicht autonome Aktionen basierend auf konfigurierten Regeln.

### Autonomie-Level

| Level | Beschreibung |
|-------|--------------|
| `off` | Keine autonomen Aktionen |
| `suggest` | Nur Vorschläge (Standard) |
| `auto_low_risk` | Automatisch bei Low-Risk |
| `auto_all` | Vollständig autonom |

### Konfigurierbare Aktionen

- Auto-Kategorisierung
- Auto-Entity-Linking
- Auto-Buchungsvorschläge
- Auto-Benachrichtigungen

---

## SmartMatchingService

Intelligentes Matching zwischen Dokumenten und Entities.

### Matching-Strategien

| Strategie | Gewicht | Beschreibung |
|-----------|---------|--------------|
| Kundennummer | 40% | Exakte Übereinstimmung |
| IBAN | 25% | Bankverbindung |
| VAT-ID | 20% | Umsatzsteuer-ID |
| Fuzzy-Name | 15% | Unscharfe Namenssuche |

### Confidence-Schwellwerte

- **> 95%**: Auto-Link ohne Review
- **75-95%**: Auto-Link mit Review-Markierung
- **50-75%**: Vorschlag zur manuellen Prüfung
- **< 50%**: Kein Match

---

## AnomalyDetectionService

Erkennt Anomalien in Dokumenten und Transaktionen.

### Anomalie-Typen

| Typ | Beschreibung |
|-----|--------------|
| `price_anomaly` | Ungewöhnlicher Preis (>2 Std-Abw.) |
| `frequency_anomaly` | Ungewöhnliche Häufigkeit |
| `amount_pattern` | Auffällige Beträge (runde Zahlen) |
| `timing_anomaly` | Ungewöhnliches Timing |
| `duplicate_risk` | Duplikat-Verdacht |

---

## OllamaService

Integration mit lokalem Ollama LLM.

### Konfiguration

```python
OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_MODEL: str = "llama2"
OLLAMA_TIMEOUT: int = 60
```

### Verwendung

```python
from app.services.ai.ollama_service import OllamaService

ollama = OllamaService()
response = await ollama.generate(
    prompt="Fasse diesen Text zusammen: ...",
    system="Du bist ein hilfreicher Assistent."
)
```

---

## LearningPipeline

ML-Pipeline für kontinuierliches Lernen.

### Pipeline-Schritte

1. **Feedback-Sammlung** - User-Korrekturen sammeln
2. **Feature-Extraktion** - Relevante Features extrahieren
3. **Model-Training** - Modell aktualisieren
4. **Evaluation** - Qualität prüfen
5. **Deployment** - Bei Verbesserung deployen

### Integration mit MLOps

Die LearningPipeline ist eng mit dem MLOps-System integriert:
- Model Registry für Versionierung
- A/B Testing für neue Modelle
- Automatischer Rollback bei Degradation

---

## Best Practices

1. **Async First**: Alle Services sind async-basiert
2. **Type Safety**: Strikte Typisierung mit TypedDict/Pydantic
3. **Error Handling**: Graceful Degradation bei LLM-Fehlern
4. **Logging**: Strukturiertes Logging mit structlog
5. **Caching**: Redis-Caching für teure Operationen
6. **Rate Limiting**: Schutz vor LLM-Überlastung

---

## Sicherheit

1. **PII-Schutz**: Sensible Daten werden nicht an LLMs gesendet
2. **Prompt Injection**: Input-Sanitierung
3. **Action Confirmation**: Kritische Aktionen erfordern Bestätigung
4. **Audit Logging**: Alle KI-Aktionen werden protokolliert
