# Feature 07: KI-Autonomie erweitern

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P2 - Wichtig
> **Geschaetzter Aufwand**: 3-4 Wochen
> **Abhaengigkeiten**: Keine (unabhaengig)

---

## Executive Summary

Die KI-Autonomie wird auf ein neues Level gehoben: Confidence-basierte Entscheidungen erlauben automatische Verarbeitung bei hoher Sicherheit, waehrend unsichere Faelle zur manuellen Pruefung gehen. Ein Self-Learning Loop verbessert die KI kontinuierlich durch User-Feedback.

**Business Value:**
- 80%+ automatische Verarbeitung
- Nur echte Ausnahmen benoetigen manuelle Arbeit
- KI wird durch Feedback besser
- 100% Audit-Trail fuer Compliance

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Confidence-Schwellen (Admin) | MUSS | 3 Stufen konfigurierbar |
| FR-02 | Auto-Kategorisierung | MUSS | Dokument-Typ >95% |
| FR-03 | Auto-Kontierung | SOLL | Buchungskonto >90% |
| FR-04 | Smart Matching | MUSS | Rechnung↔Lieferschein |
| FR-05 | Anomalie-Erkennung | SOLL | Ungewoehnliche Betraege |
| FR-06 | Self-Learning | MUSS | User-Korrekturen lernen |
| FR-07 | Explainable AI | SOLL | "Warum hat KI X entschieden?" |

---

## Confidence-basierte Autonomie

```
┌─────────────────────────────────────────────────────────────┐
│  CONFIDENCE-SCHWELLEN (Admin konfigurierbar)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  95%+ ══════════► AUTOMATISCH verarbeiten                   │
│                   └─ Audit-Log: "KI-Entscheidung"           │
│                   └─ Kein User-Eingriff noetig              │
│                                                             │
│  80-95% ════════► VORSCHLAG mit 1-Click Bestaetigung        │
│                   └─ User sieht: "KI schlaegt vor: [X]"     │
│                   └─ [Bestaetigen] [Korrigieren]            │
│                                                             │
│  <80% ══════════► MANUELLE Review Queue                     │
│                   └─ User muss aktiv entscheiden            │
│                   └─ Mehr Kontext angezeigt                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## API-Spezifikation

### Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/ai/settings` | KI-Einstellungen | Admin |
| PUT | `/api/v1/ai/settings` | Schwellen anpassen | Admin |
| GET | `/api/v1/ai/predictions/{doc_id}` | KI-Vorhersagen | Required |
| POST | `/api/v1/ai/feedback` | User-Korrektur | Required |
| GET | `/api/v1/ai/stats` | Erfolgsstatistiken | Admin |
| GET | `/api/v1/ai/explain/{prediction_id}` | Erklaerung | Required |

### `GET /api/v1/ai/predictions/{doc_id}`

**Response (200 OK):**
```json
{
  "document_id": "doc-uuid",
  "predictions": [
    {
      "id": "pred-uuid",
      "type": "document_category",
      "prediction": "eingangsrechnung",
      "confidence": 0.97,
      "alternatives": [
        {"value": "lieferschein", "confidence": 0.02},
        {"value": "angebot", "confidence": 0.01}
      ],
      "auto_applied": true,
      "explanation": "Erkannt: Rechnungsnummer, Betragsfeld, MwSt-Ausweis"
    },
    {
      "id": "pred-uuid-2",
      "type": "supplier_match",
      "prediction": {"id": "supplier-uuid", "name": "Lieferant GmbH"},
      "confidence": 0.92,
      "auto_applied": false,
      "requires_confirmation": true,
      "explanation": "Aehnlicher Name und Adresse gefunden"
    }
  ]
}
```

### `POST /api/v1/ai/feedback`

**Request:**
```json
{
  "prediction_id": "pred-uuid",
  "action": "correct",  // confirm, correct, reject
  "correct_value": "gutschrift",
  "feedback_note": "War eine Gutschrift, nicht Rechnung"
}
```

---

## Datenbank-Schema

### `ai_predictions`

```sql
CREATE TABLE ai_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) NOT NULL,

    prediction_type VARCHAR(50) NOT NULL,
    predicted_value JSONB NOT NULL,
    confidence FLOAT NOT NULL,
    alternatives JSONB DEFAULT '[]',

    model_version VARCHAR(50),
    explanation TEXT,

    auto_applied BOOLEAN DEFAULT false,
    user_confirmed BOOLEAN,
    user_corrected_value JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    feedback_at TIMESTAMPTZ,
    feedback_by_id UUID REFERENCES users(id)
);

CREATE INDEX ix_predictions_document ON ai_predictions(document_id);
CREATE INDEX ix_predictions_type ON ai_predictions(prediction_type);
CREATE INDEX ix_predictions_confidence ON ai_predictions(confidence);
```

### `ai_settings`

```sql
CREATE TABLE ai_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) UNIQUE,

    thresholds JSONB DEFAULT '{
        "auto_apply": 0.95,
        "suggest": 0.80,
        "manual": 0.0
    }',

    enabled_features JSONB DEFAULT '{
        "auto_categorization": true,
        "auto_accounting": false,
        "smart_matching": true,
        "anomaly_detection": true
    }',

    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Self-Learning Loop

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│     KI      │ ──►│    User     │ ──►│  Korrektur  │ ──►│  Training   │
│  Vorhersage │    │   prueft    │    │  speichern  │    │   Update    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                              │
                                                              ▼
                                                         Bessere
                                                        Vorhersagen
```

### Training Pipeline

```python
# app/services/ai/learning_service.py

class AILearningService:
    """Self-Learning aus User-Feedback."""

    async def process_feedback(self, feedback: AIFeedback) -> None:
        """Verarbeitet User-Feedback fuer Training."""

        # 1. Feedback speichern
        await self.store_feedback(feedback)

        # 2. Training-Sample erstellen
        if feedback.action == "correct":
            sample = TrainingSample(
                input=feedback.prediction.input_data,
                expected_output=feedback.correct_value,
                confidence_was=feedback.prediction.confidence
            )
            await self.add_to_training_queue(sample)

        # 3. Bei genuegend Samples: Model Update
        queue_size = await self.get_training_queue_size()
        if queue_size >= self.config.retrain_threshold:
            await self.trigger_model_update()

    async def trigger_model_update(self) -> None:
        """Triggert Model-Update als Celery Task."""
        from app.workers.tasks.ai_tasks import update_model
        update_model.delay()
```

---

## Implementation Tasks

### Phase 1: Confidence-System (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] Settings-Tabelle | Schwellen konfigurierbar |
| 1.2 | [ ] Prediction-Model | Confidence speichern |
| 1.3 | [ ] Auto-Apply Logic | >95% automatisch |
| 1.4 | [ ] Review Queue | <80% in Queue |

### Phase 2: KI-Features (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Auto-Kategorisierung | Dokument-Typ |
| 2.2 | [ ] Smart Matching | Rechnung↔Lieferschein |
| 2.3 | [ ] Anomalie-Erkennung | Ungewoehnliche Betraege |
| 2.4 | [ ] Explainable Output | Erklaerung generiert |

### Phase 3: Self-Learning (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Feedback-API | Korrekturen speichern |
| 3.2 | [ ] Training Queue | Samples gesammelt |
| 3.3 | [ ] Model Update Task | Retraining funktioniert |
| 3.4 | [ ] Metriken | Verbesserung messbar |

### Phase 4: Frontend (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 4.1 | [ ] Prediction UI | Confidence sichtbar |
| 4.2 | [ ] Feedback Buttons | Bestaetigen/Korrigieren |
| 4.3 | [ ] Admin Settings | Schwellen anpassen |
| 4.4 | [ ] Stats Dashboard | Erfolgsrate sichtbar |

---

## Quality Gates

- [ ] Auto-Apply bei >95% funktioniert
- [ ] Review-Queue fuer unsichere Faelle
- [ ] Feedback wird gespeichert
- [ ] Audit-Trail fuer alle Entscheidungen
- [ ] Erklaerungen sind hilfreich
