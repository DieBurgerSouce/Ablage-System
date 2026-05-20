# MLOps Services

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält die MLOps-Infrastruktur für Model Lifecycle Management, automatisches Retraining und Qualitätsmonitoring.

---

## Services

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **ModelRegistry** | `model_registry.py` | Model Versioning, Deployment, Rollback |
| **RetrainingService** | `retraining_service.py` | Automatisches Retraining, Evaluation |

---

## ModelRegistry

Zentrale Registry für alle ML-Modelle im System.

### Model-Typen

| Typ | Code | Beschreibung |
|-----|------|--------------|
| OCR Confidence | `ocr_confidence` | Confidence-Kalibrierung pro Backend |
| Backend Router | `ocr_backend_router` | Routing-Entscheidung pro Dokument |
| Document Classifier | `document_classifier` | Dokumenttyp-Klassifikation |
| Entity Matcher | `entity_matcher` | Entity-Matching-Modell |
| Amount Extractor | `amount_extractor` | Betragsextraktion |
| Date Extractor | `date_extractor` | Datumsextraktion |

### Model Lifecycle

```
┌──────────┐     ┌───────────┐     ┌────────┐     ┌────────────┐
│  DRAFT   │ ──► │ CANDIDATE │ ──► │ ACTIVE │ ──► │ DEPRECATED │
└──────────┘     └───────────┘     └────────┘     └────────────┘
                       │                                ▲
                       ▼                                │
                 ┌─────────────┐                  ┌──────────┐
                 │ ROLLED_BACK │ ◄────────────────│ ARCHIVED │
                 └─────────────┘                  └──────────┘
```

### Status-Beschreibungen

| Status | Beschreibung |
|--------|--------------|
| `draft` | In Entwicklung, nicht deployed |
| `candidate` | A/B Test läuft |
| `active` | Produktiv im Einsatz |
| `deprecated` | Veraltet, wird nicht mehr genutzt |
| `rolled_back` | Zurückgerollt wegen Qualitätsproblemen |
| `archived` | Archiviert, >90 Tage inaktiv |

### API

```python
from app.services.mlops.model_registry import ModelRegistry

registry = ModelRegistry(db)

# Model registrieren
version = await registry.register_model(
    model_type="ocr_confidence",
    version="v2.3.1",
    metadata={
        "training_data_size": 12450,
        "accuracy": 0.89,
        "training_date": "2026-01-20"
    }
)

# Aktuelles Modell abrufen
active_model = await registry.get_active_model("ocr_confidence")

# Rollback durchführen
await registry.rollback(
    model_type="ocr_confidence",
    to_version="v2.3.0",
    reason="Qualitätsverschlechterung"
)
```

---

## RetrainingService

Orchestriert automatisches Modell-Retraining.

### Retraining-Trigger

| Trigger | Code | Bedingung |
|---------|------|-----------|
| Threshold | `threshold` | 100+ unverarbeitete Korrekturen |
| Scheduled | `scheduled` | Wöchentlich Sonntag 02:00 |
| Drift | `drift` | Qualitäts-Drift erkannt |
| Manual | `manual` | Admin-Trigger |
| A/B Winner | `ab_test_winner` | A/B Test Gewinner |

### Retraining-Pipeline

```
1. Daten sammeln (Korrekturen seit letztem Training)
        ↓
2. Feature Engineering
        ↓
3. Model Training (GPU Queue)
        ↓
4. Evaluation gegen Hold-Out Set
        ↓
5. Vergleich mit aktivem Modell
        ↓
6. Entscheidung: Promote / Reject / A/B Test
        ↓
7. Bei Erfolg: Deployment als CANDIDATE
        ↓
8. Nach A/B Test: Promotion zu ACTIVE
```

### API

```python
from app.services.mlops.retraining_service import RetrainingService

service = RetrainingService(db)

# Manuelles Retraining starten
job = await service.trigger_retraining(
    model_type="ocr_confidence",
    trigger="manual",
    force=False
)

# Retraining-Status prüfen
status = await service.get_job_status(job.id)
# status.state: "pending" | "running" | "completed" | "failed"

# Modell evaluieren
metrics = await service.evaluate_model(
    model_type="ocr_confidence",
    version="v2.3.1"
)
```

---

## Celery Tasks

| Task | Schedule | Queue | Beschreibung |
|------|----------|-------|--------------|
| `mlops.check_retraining_threshold` | Täglich 03:00 | maintenance | Prüft ob Retraining nötig |
| `mlops.run_retraining` | On-Demand | gpu | Führt Retraining durch (max 1h) |
| `mlops.evaluate_model` | Nach Training | maintenance | Evaluiert neues Modell |
| `mlops.rollback_if_degraded` | Stündlich | maintenance | Automatischer Rollback |
| `mlops.cleanup_old_versions` | Wöchentlich | maintenance | Archiviert alte Versionen |
| `mlops.get_stats` | On-Demand | metadata | MLOps Statistiken |

---

## Datenmodell

Die MLOps-Daten werden in JSONB-Feldern in der AppConfig-Tabelle gespeichert:

### Model Registry

```python
MODEL_REGISTRY_KEY = "mlops_model_registry"

{
    "models": {
        "ocr_confidence": {
            "active_version": "v2.3.1",
            "versions": {
                "v2.3.1": {
                    "status": "active",
                    "created_at": "2026-01-20T02:00:00Z",
                    "deployed_at": "2026-01-25T02:00:00Z",
                    "metrics": {
                        "accuracy": 0.89,
                        "precision": 0.91,
                        "recall": 0.87
                    },
                    "training_data": {
                        "size": 12450,
                        "from_date": "2025-01-01",
                        "to_date": "2026-01-19"
                    }
                },
                "v2.3.0": {
                    "status": "deprecated",
                    ...
                }
            }
        }
    }
}
```

### Retraining Config

```python
RETRAINING_CONFIG_KEY = "mlops_retraining_config"

{
    "ocr_confidence": {
        "threshold_corrections": 100,
        "schedule": "0 2 * * 0",  # Sonntag 02:00
        "max_training_time_minutes": 60,
        "min_improvement_percent": 2.0,
        "rollback_degradation_percent": 5.0
    }
}
```

### Retraining Jobs

```python
RETRAINING_JOBS_KEY = "mlops_retraining_jobs"

{
    "jobs": [
        {
            "id": "job-123",
            "model_type": "ocr_confidence",
            "trigger": "threshold",
            "state": "completed",
            "started_at": "2026-01-20T02:00:00Z",
            "completed_at": "2026-01-20T02:45:00Z",
            "result": {
                "new_version": "v2.3.1",
                "improvement": 0.03,
                "promoted": true
            }
        }
    ]
}
```

---

## Qualitätsmetriken

### Überwachte Metriken

| Metrik | Beschreibung | Schwellwert |
|--------|--------------|-------------|
| Accuracy | Gesamtgenauigkeit | >85% |
| Precision | Präzision | >80% |
| Recall | Recall | >80% |
| F1-Score | F1 | >82% |
| Latency P95 | 95. Perzentil Latenz | <2s |

### Drift-Erkennung

Der Service überwacht Modell-Drift durch:

1. **Feature Drift**: Verteilung der Input-Features
2. **Prediction Drift**: Verteilung der Vorhersagen
3. **Performance Drift**: Accuracy über Zeit

Bei erkanntem Drift wird automatisch Retraining getriggert.

---

## Integration

### Mit OCR Self-Learning

```
User-Korrektur
     ↓
OCR Learning Service (Feedback)
     ↓
Threshold erreicht?
     ↓ Ja
MLOps: Retraining triggern
     ↓
Neues Modell trainieren
     ↓
A/B Test starten
     ↓
Bei Erfolg: Promotion
```

### Mit Alert Center

Bei kritischen MLOps-Events werden Alerts erstellt:

| Event | Alert-Code | Severity |
|-------|------------|----------|
| Training fehlgeschlagen | `MLOPS_TRAIN_FAILED` | high |
| Automatischer Rollback | `MLOPS_ROLLBACK` | critical |
| Modell degradiert | `MLOPS_DEGRADATION` | high |
| Retraining nötig | `MLOPS_RETRAINING` | medium |

---

## Best Practices

1. **Versionierung**: Jedes Modell hat semantische Versionierung
2. **Reproducibility**: Training-Parameter werden gespeichert
3. **A/B Testing**: Neue Modelle immer erst in A/B Test
4. **Rollback Ready**: Jederzeit Rollback zu vorherigem Modell
5. **Monitoring**: Kontinuierliche Qualitätsüberwachung
6. **Audit Trail**: Alle Änderungen werden protokolliert

---

## Sicherheit

1. **GPU Isolation**: Training läuft in separater Queue
2. **Resource Limits**: Max 1h Training, max 12GB VRAM
3. **Admin Only**: Manuelle Trigger nur für Admins
4. **Data Privacy**: Training nur auf anonymisierten Daten
