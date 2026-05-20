# OCR Self-Learning API

## Übersicht

Die OCR Self-Learning API ermöglicht kontinuierliches Lernen des OCR-Systems basierend auf Benutzer-Feedback. Sie bietet Confidence-Kalibrierung, A/B-Testing von Modell-Versionen und verschiedene Lernmodi.

**Basis-URL**: `/api/v1/ocr-learning`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt

---

## Lernmodi

| Modus | Beschreibung |
|-------|--------------|
| `aggressive` | Jede Korrektur fließt sofort ein |
| `cautious` | Nur verifizierte Korrekturen |
| `batch` | Tägliche Batch-Verarbeitung |

---

## Erlaubte OCR-Backends

Die folgenden Backends sind für Feedback zugelassen (Whitelist):

- `deepseek`
- `got_ocr`
- `surya`
- `surya_gpu`
- `docling`

---

## Endpunkte

### Feedback

#### POST /ocr-learning/feedback

Übermittelt eine Benutzer-Korrektur.

**Request Body**:
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "field_name": "invoice_number",
  "ocr_backend": "deepseek",
  "original_value": "RE-2O26-OO1234",
  "corrected_value": "RE-2026-001234",
  "original_confidence": 0.78,
  "correction_type": "text"
}
```

**Correction Types**:
- `text` - Textkorrektur
- `amount` - Betragskorrektur
- `date` - Datumskorrektur
- `entity` - Entity-Korrektur

**Validierung**:
- `ocr_backend`: Muss in ALLOWED_OCR_BACKENDS sein
- `field_name`: Pattern `^[a-zA-Z][a-zA-Z0-9_]{0,63}$`
- `original_confidence`: 0.0 - 1.0

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "status": "accepted",
  "learning_mode": "aggressive",
  "applied_immediately": true,
  "confidence_adjustment": -0.02,
  "message": "Korrektur erfolgreich verarbeitet"
}
```

---

### Kalibrierung

#### POST /ocr-learning/calibrate

Berechnet kalibrierte Confidence basierend auf historischen Korrekturen.

**Request Body**:
```json
{
  "ocr_backend": "deepseek",
  "field_name": "invoice_number",
  "raw_confidence": 0.85
}
```

**Response** (200):
```json
{
  "raw_confidence": 0.85,
  "calibrated_confidence": 0.82,
  "adjustment": -0.03,
  "adjustments_applied": [
    {
      "level": "backend",
      "backend": "deepseek",
      "adjustment": -0.02
    },
    {
      "level": "field",
      "backend": "deepseek",
      "field": "invoice_number",
      "adjustment": -0.01
    }
  ],
  "sample_size": 1250,
  "last_updated": "2026-01-27T10:00:00Z"
}
```

---

### Statistiken

#### GET /ocr-learning/confidence-stats

Ruft Confidence-Statistiken ab.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `backend` | string | Filter nach Backend |
| `field` | string | Filter nach Feldname |
| `period` | string | `day`, `week`, `month` (default: week) |

**Response** (200):
```json
{
  "period": "week",
  "overall": {
    "total_corrections": 487,
    "avg_original_confidence": 0.81,
    "avg_corrected_confidence": 0.95,
    "correction_rate": 0.12
  },
  "by_backend": [
    {
      "backend": "deepseek",
      "corrections": 312,
      "avg_confidence": 0.83,
      "adjustment": -0.02,
      "trend": "improving"
    },
    {
      "backend": "got_ocr",
      "corrections": 175,
      "avg_confidence": 0.79,
      "adjustment": -0.04,
      "trend": "stable"
    }
  ],
  "by_field": [
    {
      "field": "invoice_number",
      "corrections": 89,
      "common_errors": ["O→0", "l→1"],
      "avg_confidence": 0.76
    },
    {
      "field": "total_amount",
      "corrections": 124,
      "common_errors": ["Dezimaltrenner", "Tausender"],
      "avg_confidence": 0.82
    }
  ],
  "top_error_patterns": [
    {
      "pattern": "O→0",
      "count": 45,
      "affected_backends": ["got_ocr"]
    },
    {
      "pattern": "ü→u",
      "count": 28,
      "affected_backends": ["surya"]
    }
  ]
}
```

---

#### GET /ocr-learning/stats

Allgemeine Learning-Statistiken.

**Response** (200):
```json
{
  "learning_mode": "aggressive",
  "total_corrections": 12450,
  "corrections_this_week": 487,
  "model_version": "v2.3.1",
  "last_retrain": "2026-01-20T02:00:00Z",
  "next_scheduled_retrain": "2026-01-27T02:00:00Z",
  "pending_corrections": 0,
  "active_ab_tests": 1,
  "quality_metrics": {
    "accuracy_before_learning": 0.81,
    "accuracy_after_learning": 0.89,
    "improvement": 0.08
  }
}
```

---

### A/B Testing

#### POST /ocr-learning/ab-test/start

Startet einen A/B-Test zwischen Modell-Versionen.

**Berechtigungen**: Admin erforderlich

**Request Body**:
```json
{
  "test_id": "umlaut_improvement_v2",
  "description": "Test verbesserte Umlaut-Erkennung",
  "variant_a": {
    "name": "current",
    "model_version": "v2.3.0",
    "description": "Aktuelle Produktion"
  },
  "variant_b": {
    "name": "candidate",
    "model_version": "v2.3.1",
    "description": "Verbesserte Umlaute"
  },
  "traffic_split": 0.2,
  "duration_days": 7,
  "metrics_to_track": ["accuracy", "confidence", "correction_rate"]
}
```

**Validierung**:
- `test_id`: Pattern `^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$`
- Länge: 3-64 Zeichen
- Keine Path-Traversal-Zeichen

**Response** (201):
```json
{
  "test_id": "umlaut_improvement_v2",
  "status": "running",
  "started_at": "2026-01-27T10:00:00Z",
  "ends_at": "2026-02-03T10:00:00Z",
  "traffic_split": {
    "variant_a": 0.8,
    "variant_b": 0.2
  }
}
```

---

#### GET /ocr-learning/ab-test/{test_id}

Ruft Ergebnisse eines A/B-Tests ab.

**Response** (200):
```json
{
  "test_id": "umlaut_improvement_v2",
  "status": "running",
  "started_at": "2026-01-27T10:00:00Z",
  "ends_at": "2026-02-03T10:00:00Z",
  "current_results": {
    "variant_a": {
      "name": "current",
      "sample_size": 1250,
      "accuracy": 0.84,
      "avg_confidence": 0.81,
      "correction_rate": 0.12,
      "umlaut_accuracy": 0.92
    },
    "variant_b": {
      "name": "candidate",
      "sample_size": 310,
      "accuracy": 0.88,
      "avg_confidence": 0.85,
      "correction_rate": 0.08,
      "umlaut_accuracy": 0.97
    }
  },
  "statistical_significance": {
    "is_significant": true,
    "p_value": 0.023,
    "confidence_interval": 0.95,
    "winner": "variant_b",
    "improvement": "+4.8% Accuracy"
  },
  "recommendation": "Kandidat zeigt signifikante Verbesserung. Deployment empfohlen."
}
```

---

#### POST /ocr-learning/ab-test/{test_id}/end

Beendet einen A/B-Test vorzeitig.

**Berechtigungen**: Admin erforderlich

**Request Body**:
```json
{
  "action": "promote_winner",
  "winner": "variant_b"
}
```

**Actions**:
- `promote_winner` - Gewinner in Produktion übernehmen
- `abort` - Test abbrechen ohne Änderung
- `extend` - Test verlängern (duration_days erforderlich)

**Response** (200):
```json
{
  "test_id": "umlaut_improvement_v2",
  "status": "completed",
  "ended_at": "2026-01-27T15:00:00Z",
  "action_taken": "promote_winner",
  "promoted_version": "v2.3.1",
  "final_results": { ... }
}
```

---

### Modus-Steuerung

#### POST /ocr-learning/mode/{mode}

Setzt den Lernmodus.

**Berechtigungen**: Admin erforderlich

**Path-Parameter**:
- `mode`: `aggressive`, `cautious`, oder `batch`

**Response** (200):
```json
{
  "previous_mode": "batch",
  "current_mode": "aggressive",
  "changed_at": "2026-01-27T15:00:00Z",
  "changed_by": "admin@firma.de",
  "pending_corrections_processed": 45
}
```

---

### Modell-Version

#### GET /ocr-learning/model-version

Ruft die aktuelle Modell-Version ab.

**Response** (200):
```json
{
  "current_version": "v2.3.1",
  "deployed_at": "2026-01-25T02:00:00Z",
  "previous_version": "v2.3.0",
  "training_data": {
    "corrections_used": 12450,
    "date_range": {
      "from": "2025-01-01",
      "to": "2026-01-24"
    }
  },
  "performance": {
    "accuracy": 0.89,
    "vs_previous": "+0.03"
  },
  "lifecycle_status": "active"
}
```

---

## Confidence-Adjustments Struktur

Die Kalibrierungsdaten werden in JSONB gespeichert:

```json
{
  "backend": {
    "deepseek": -0.02,
    "got_ocr": -0.04,
    "surya": -0.05
  },
  "field": {
    "deepseek": {
      "invoice_number": -0.01,
      "total_amount": 0.01
    },
    "got_ocr": {
      "invoice_number": -0.03
    }
  },
  "learning_mode": "aggressive",
  "updated_at": "2026-01-27T10:00:00Z"
}
```

---

## Input-Validierung (Sicherheit)

### Backend-Whitelist

```python
ALLOWED_OCR_BACKENDS = frozenset({
    "deepseek", "got_ocr", "surya", "surya_gpu", "docling"
})
```

### Feldname-Pattern

```python
ALLOWED_FIELD_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$"
```

### Test-ID-Pattern

```python
ALLOWED_TEST_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$"
```

### Korrektur-Typen

```python
ALLOWED_CORRECTION_TYPES = {"text", "amount", "date", "entity"}
```

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `LEARNING_INVALID_BACKEND` | 400 | Backend nicht in Whitelist |
| `LEARNING_INVALID_FIELD` | 400 | Feldname ungültig |
| `LEARNING_INVALID_CONFIDENCE` | 422 | Confidence außerhalb 0.0-1.0 |
| `LEARNING_TEST_NOT_FOUND` | 404 | A/B-Test nicht gefunden |
| `LEARNING_TEST_ALREADY_EXISTS` | 409 | Test-ID existiert bereits |
| `LEARNING_TEST_ALREADY_ENDED` | 409 | Test bereits beendet |
| `LEARNING_INVALID_MODE` | 400 | Ungültiger Lernmodus |

---

## Celery Tasks

| Task | Schedule | Beschreibung |
|------|----------|--------------|
| `ocr_learning.process_batch` | Täglich 02:00 | Batch-Korrekturen verarbeiten |
| `ocr_learning.update_calibration` | Alle 4h | Kalibrierung aktualisieren |
| `ocr_learning.check_ab_tests` | Stündlich | A/B-Test-Fristen prüfen |
| `ocr_learning.generate_stats` | Täglich 06:00 | Statistiken generieren |

---

## Sicherheitshinweise

1. **Input-Validierung**: Strikte Whitelist für Backends, Feldnamen, Test-IDs
2. **Path-Traversal-Schutz**: Test-IDs werden validiert
3. **Admin-Only**: A/B-Tests und Modus-Änderung nur für Admins
4. **Rate Limiting**: Max. 100 Feedback-Anfragen/Minute
5. **Audit-Trail**: Alle Änderungen werden protokolliert

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
