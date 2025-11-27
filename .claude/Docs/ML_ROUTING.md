# ML-Routing System Dokumentation

## Uebersicht

Das Ablage-System verfuegt ueber ein vollstaendiges Enterprise ML-Routing System zur intelligenten Backend-Auswahl fuer OCR-Verarbeitung.

## Komponenten

### 1. Drift Detection (`app/ml/drift_detector.py`)

Erkennt Verteilungsaenderungen in den Eingabedaten (Data Drift).

**Features:**
- Kolmogorov-Smirnov Test fuer numerische Features
- Chi-Square Test fuer kategorische Features
- Population Stability Index (PSI)
- Konfigurierbare Schwellwerte und Fenstergroessen

**Nutzung:**
```python
from app.ml.drift_detector import get_drift_detector, DriftSeverity

detector = get_drift_detector()

# Sample hinzufuegen
detector.add_sample(
    features={"quality_score": 0.85, "complexity": "high"},
    prediction="deepseek"
)

# Drift erkennen
report = detector.detect_drift()
print(f"Drift-Score: {report.overall_drift_score}")
print(f"Schweregrad: {report.severity.value}")
```

**Schweregrade:**
- `none`: < 0.1 - Kein Drift
- `low`: 0.1-0.3 - Leichter Drift
- `medium`: 0.3-0.5 - Moderater Drift
- `high`: 0.5-0.7 - Hoher Drift
- `critical`: > 0.7 - Kritischer Drift

### 2. SHAP Explainability (`app/ml/shap_explainer.py`)

Erklaert ML-Routing-Entscheidungen mittels SHAP-Werten.

**Features:**
- Feature-Contributions pro Entscheidung
- Globale Feature-Importance
- Deutsche Erklaerungstexte
- Counterfactual-Analyse (was waere wenn)

**Nutzung:**
```python
from app.ml.shap_explainer import get_shap_explainer

explainer = get_shap_explainer()

explanation = explainer.explain_routing(
    document_id="doc_001",
    features={"quality_score": 0.85, "has_tables": True},
    selected_backend="deepseek",
    confidence=0.88,
    all_probabilities={"deepseek": 0.55, "got_ocr": 0.30, "surya": 0.15}
)

print(explanation.decision_summary)
# Output: "DeepSeek wurde mit 88% Konfidenz gewaehlt..."
```

### 3. A/B Testing (`app/ml/ab_testing.py`)

Framework fuer kontrollierte Experimente zur Backend-Optimierung.

**Features:**
- Sticky/Random/Round-Robin Traffic-Allocation
- Statistische Signifikanztests
- Automatische Experiment-Abschluss-Pruefung
- Persistente Experiment-Speicherung

**Nutzung:**
```python
from app.ml.ab_testing import get_ab_test_manager, create_routing_experiment

# Schnelles Experiment erstellen
experiment = create_routing_experiment(
    name="DeepSeek vs GOT-OCR",
    control_backend="deepseek",
    treatment_backend="got_ocr",
    traffic_split=0.5
)

# Variante fuer Dokument abrufen
manager = get_ab_test_manager()
variant = manager.get_variant(experiment.experiment_id, "doc_123")

# Ergebnis aufzeichnen
manager.record_result(
    experiment_id=experiment.experiment_id,
    variant_name=variant.name,
    success=True,
    latency_ms=1500.0,
    accuracy=0.95
)

# Experiment abschliessen
winner = manager.conclude_experiment(experiment.experiment_id)
print(f"Gewinner: {winner}")
```

### 4. Prometheus Metriken (`app/ml/metrics.py`)

Vollstaendige Observability fuer ML-Operationen.

**Metriken:**
- `ml_routing_requests_total` - Routing-Anfragen
- `ml_routing_latency_seconds` - Routing-Latenz
- `ml_routing_confidence` - Routing-Konfidenz
- `ml_drift_overall_score` - Drift-Score
- `ml_ab_experiment_samples_total` - A/B Samples
- `ml_gpu_memory_used_bytes` - GPU-Speicher

**Nutzung:**
```python
from app.ml.metrics import get_ml_metrics

metrics = get_ml_metrics()

# Routing tracken
metrics.record_routing_request(
    method="ml",
    backend="deepseek",
    status="success",
    latency_seconds=0.025,
    confidence=0.92
)

# Decorator fuer automatisches Tracking
from app.ml.metrics import track_routing

@track_routing(method="ml")
async def route_document(features):
    # Routing-Logik
    pass
```

## API Endpoints

### Drift Detection

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/v1/ml/drift/status` | GET | Aktueller Drift-Status |
| `/api/v1/ml/drift/detect` | POST | Drift-Detection ausfuehren |
| `/api/v1/ml/drift/history` | GET | Drift-Historie |
| `/api/v1/ml/drift/reset` | POST | Reference-Window zuruecksetzen |

### SHAP Explainability

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/v1/ml/explain/routing` | POST | Routing erklaeren |
| `/api/v1/ml/explain/global` | GET | Globale Feature-Importance |
| `/api/v1/ml/explain/{doc_id}` | GET | Erklaerung abrufen |

### A/B Testing

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/v1/ml/experiments` | GET | Alle Experimente |
| `/api/v1/ml/experiments` | POST | Neues Experiment |
| `/api/v1/ml/experiments/{id}` | GET | Experiment-Details |
| `/api/v1/ml/experiments/{id}/start` | POST | Experiment starten |
| `/api/v1/ml/experiments/{id}/conclude` | POST | Experiment abschliessen |
| `/api/v1/ml/experiments/{id}/variant/{doc_id}` | GET | Variante abrufen |
| `/api/v1/ml/experiments/{id}/result` | POST | Ergebnis aufzeichnen |

### Metriken

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/v1/ml/metrics` | GET | Prometheus Metriken |
| `/api/v1/ml/report` | GET | ML-Status-Report |

## Celery Tasks

### Periodische Tasks

| Task | Intervall | Beschreibung |
|------|-----------|--------------|
| `run_drift_detection` | Stuendlich | Drift-Detection ausfuehren |
| `update_ml_metrics` | 30 Sek | Metriken aktualisieren |
| `check_experiment_completion` | 5 Min | Experimente pruefen |
| `generate_ml_report` | Taeglich | ML-Report generieren |

**Celery Beat Konfiguration:**
```python
from app.workers.tasks.ml_tasks import CELERY_BEAT_ML_SCHEDULE

# In celery_app.py
app.conf.beat_schedule.update(CELERY_BEAT_ML_SCHEDULE)
```

### MLTracker Helper

Der `MLTracker` ermoeglicht einfaches Tracking in OCR-Tasks:

```python
from app.workers.tasks.ml_tasks import ml_tracker

# Routing-Entscheidung tracken
ml_tracker.track_routing_decision(
    document_id="doc_001",
    features={"quality": 0.9},
    selected_backend="deepseek",
    confidence=0.85,
    routing_method="ml",
    latency_ms=25.0
)

# OCR-Ergebnis tracken
ml_tracker.track_ocr_result(
    document_id="doc_001",
    backend="deepseek",
    success=True,
    processing_time_ms=1500.0,
    accuracy=0.95
)
```

## Grafana Dashboard

Das ML-Dashboard (`infrastructure/grafana/dashboards/ablage-ml-routing.json`) visualisiert:

- **Routing Uebersicht**: Anfragen/Min, ML-Anteil, Drift-Score
- **Drift Detection**: Gauge, Verlauf, Feature-Scores, Alerts
- **A/B Testing**: Samples, Conversion Rates
- **Backend Performance**: Verarbeitungszeit, Genauigkeit
- **GPU/Model**: VRAM-Nutzung, Inferenz-Zeit

### Alerts

Konfigurierte Grafana-Alerts (`infrastructure/grafana/provisioning/alerting/ml-alerts.yml`):

- **Kritischer Drift**: Drift-Score > 0.5 (5 Min)
- **Hoher Drift**: Drift-Score > 0.3 (15 Min)
- **Niedrige Konfidenz**: Median < 70% (10 Min)
- **Hohe Latenz**: p95 > 100ms (5 Min)
- **GPU kritisch**: VRAM > 90% (2 Min)
- **Backend langsam**: p95 > 10s (5 Min)

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  ML Router  │──│  Drift Det  │──│ SHAP Expl.  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│         │                │                │                  │
│         └────────────────┼────────────────┘                  │
│                          │                                   │
│                   ┌──────┴──────┐                           │
│                   │ A/B Manager │                           │
│                   └─────────────┘                           │
│                          │                                   │
├──────────────────────────┼───────────────────────────────────┤
│  Celery Workers          │          Prometheus               │
│  ┌─────────────┐         │          ┌─────────────┐          │
│  │ ML Tasks    │─────────┴─────────│  ML Metrics │          │
│  └─────────────┘                    └─────────────┘          │
├──────────────────────────────────────────────────────────────┤
│                     Grafana Dashboards                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ML-Routing: Drift | A/B Tests | SHAP | Backend Perf    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Best Practices

### Drift Detection

1. **Min 100 Samples** fuer zuverlaessige Detection
2. **Reference-Window** nach Retraining zuruecksetzen
3. **Alerts konfigurieren** fuer severity >= medium

### A/B Testing

1. **Mindestens 1000 Samples** pro Variante
2. **Signifikanz pruefen** vor Schlussfolgerungen
3. **Ein Experiment** gleichzeitig pro Backend-Paar

### SHAP Explainability

1. **Top-5 Features** fuer Benutzer anzeigen
2. **German explanations** fuer deutsche Dokumente
3. **Global importance** regelmaessig ueberpruefen

## Troubleshooting

### Kein Drift erkannt trotz Aenderungen

- Pruefen ob min_samples erreicht
- Reference-Window pruefen (default 7 Tage)
- Feature-Extraktion konsistent?

### A/B Experiment keine Samples

- Experiment gestartet (`status == running`)?
- Traffic-Prozentsatz pruefen
- get_variant() korrekt aufgerufen?

### SHAP Erklaerungen leer

- SHAP-Model geladen?
- Features korrekt extrahiert?
- Pruefen: `explainer._shap_available`

## Dateien

```
app/ml/
├── __init__.py           # Modul-Exports
├── drift_detector.py     # Drift Detection
├── shap_explainer.py     # SHAP Explainability
├── ab_testing.py         # A/B Testing Framework
└── metrics.py            # Prometheus Metriken

app/api/v1/
└── ml.py                 # ML API Endpoints

app/workers/tasks/
└── ml_tasks.py           # Celery ML Tasks

infrastructure/grafana/
├── dashboards/
│   └── ablage-ml-routing.json   # ML Dashboard
└── provisioning/alerting/
    └── ml-alerts.yml     # Alert Rules

tests/
├── unit/
│   ├── test_drift_detector.py
│   └── test_ab_testing.py
└── integration/
    └── test_ml_routing_integration.py
```

## Changelog

### v2.0.0 (2025-11)
- Initiale ML-Routing Implementation
- Drift Detection mit KS/Chi-Square/PSI
- SHAP Explainability
- A/B Testing Framework
- Prometheus Metriken
- Grafana Dashboard und Alerts
- Celery Task Integration
- 311 Tests (Unit + Integration)
