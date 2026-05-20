# OCR Self-Learning System (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: Keine DB-Migration erforderlich (JSONB-basiert)

**Core Service**: `SelfLearningOCRService` (`app/services/ocr/self_learning_service.py`)

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Confidence-Kalibrierung | EMA-basierte Anpassung basierend auf User-Korrekturen |
| A/B Testing | Vergleich von Modell-Versionen mit Traffic-Split |
| Learning Modes | Aggressive (sofort), Cautious (verifiziert), Batch (taeglich) |
| Rollback | Automatischer Rollback bei Qualitaetsverschlechterung |

**Learning Modes**:
- `aggressive`: Jede User-Korrektur fliesst sofort ins System ein
- `cautious`: Nur verifizierte Korrekturen werden uebernommen
- `batch`: Korrekturen werden taeglich im Batch verarbeitet

**API Endpoints** (alle erfordern Authentifizierung):
- `POST /api/v1/ocr-learning/feedback` - Korrektur-Feedback uebermitteln
- `POST /api/v1/ocr-learning/calibrate` - Kalibrierte Confidence abrufen
- `GET /api/v1/ocr-learning/confidence-stats` - Confidence-Statistiken
- `POST /api/v1/ocr-learning/ab-test/start` - A/B Test starten (Admin)
- `GET /api/v1/ocr-learning/ab-test/{test_id}` - Test-Ergebnis abrufen
- `POST /api/v1/ocr-learning/ab-test/{test_id}/end` - Test beenden (Admin)
- `GET /api/v1/ocr-learning/stats` - Learning-Statistiken
- `POST /api/v1/ocr-learning/mode/{mode}` - Learning-Modus setzen (Admin)
- `GET /api/v1/ocr-learning/model-version` - Aktuelle Modell-Version

**Datenmodell (JSONB in AppConfig)**:
```python
CONFIDENCE_ADJUSTMENTS_KEY = "ocr_confidence_adjustments"
# Struktur:
{
    "backend": {"deepseek": -0.05, "got_ocr": 0.02},
    "field": {"deepseek": {"invoice_number": -0.03}},  # [backend][field] = adjustment
    "learning_mode": "aggressive",
    "updated_at": "2026-01-19T12:00:00Z"
}
```

**Frontend**:
- Route: `/admin/ocr-learning`
- Dashboard mit Statistiken, A/B Test Management, Mode Selection
- Komponenten: LearningStatsCards, ConfidenceAdjustmentsChart, ABTestCard, etc.

**SECURITY (Input-Validierung)**:
- OCR-Backends: Whitelist-Validierung (`ALLOWED_OCR_BACKENDS`)
- Feldnamen: Regex-Pattern (`^[a-zA-Z][a-zA-Z0-9_]{0,63}$`)
- Korrektur-Typen: Whitelist (`text`, `amount`, `date`, `entity`)
- Confidence-Werte: Range-Validierung (0.0 - 1.0)
- Test-IDs: Regex-Pattern (`^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$`) - Laengenbegrenzung 3-64 Zeichen, Path-Traversal-Schutz
