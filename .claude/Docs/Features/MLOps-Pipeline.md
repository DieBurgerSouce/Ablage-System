# MLOps Pipeline (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: Keine (JSONB in AppConfig)

**Core Services**:
- `ModelRegistry` (`app/services/mlops/model_registry.py`) - Model Versioning, Rollback
- `RetrainingService` (`app/services/mlops/retraining_service.py`) - Retraining Orchestration

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Model Versioning | Versionierte Modelle mit Lineage-Tracking |
| Automatic Retraining | Bei 100+ Korrekturen oder woechentlich |
| Quality Monitoring | Automatische Rollback bei >5% Degradation |
| Model Lifecycle | DRAFT -> CANDIDATE -> ACTIVE -> DEPRECATED |

**Model Types**:
- `ocr_confidence` - OCR Confidence Calibration
- `ocr_backend_router` - Backend Selection Router
- `document_classifier` - Document Type Classification
- `entity_matcher` - Entity Matching Model
- `amount_extractor` - Amount/Currency Extraction
- `date_extractor` - Date Extraction

**Retraining Triggers**:
- `threshold` - 100+ unverarbeitete Korrekturen
- `scheduled` - Woechentlich Sonntag 02:00
- `drift` - Qualitaets-Drift erkannt
- `manual` - Admin-Trigger
- `ab_test_winner` - A/B Test Gewinner

**Celery Tasks**:
- `mlops.check_retraining_threshold` - Taeglich 03:00 (maintenance queue)
- `mlops.run_retraining` - GPU queue, max 1h
- `mlops.evaluate_model` - Nach Training, entscheidet Promotion
- `mlops.rollback_if_degraded` - Automatisch bei Qualitaetsverlust
- `mlops.cleanup_old_versions` - Woechentlich, archiviert >90 Tage
- `mlops.get_stats` - MLOps Statistiken abrufen

**Model Lifecycle**:
```
DRAFT -> CANDIDATE -> ACTIVE -> DEPRECATED
                   |
             ROLLED_BACK -> ARCHIVED
```

**Datenmodell (JSONB in AppConfig)**:
```python
MODEL_REGISTRY_KEY = "mlops_model_registry"
RETRAINING_CONFIG_KEY = "mlops_retraining_config"
RETRAINING_JOBS_KEY = "mlops_retraining_jobs"
```
