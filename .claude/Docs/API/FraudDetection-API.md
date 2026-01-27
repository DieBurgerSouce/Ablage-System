# Fraud Detection API

## Übersicht

Die Fraud Detection API bietet KI-gestützte Betrugserkennung für Dokumente und Geschäftspartner. Sie identifiziert verdächtige Muster wie Duplikat-Rechnungen, Preisanomalien und fiktive Lieferanten.

**Basis-URL**: `/api/v1/fraud`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt

---

## Betrugstypen

| Typ | Beschreibung | Risiko |
|-----|--------------|--------|
| `duplicate_invoice` | Doppelt eingereichte Rechnungen | HIGH |
| `price_anomaly` | Ungewöhnliche Preisabweichungen | MEDIUM |
| `phantom_supplier` | Fiktive/nicht existierende Lieferanten | CRITICAL |
| `expense_fraud` | Spesen-Missbrauch | HIGH |
| `kickback` | Provisionsschema-Verdacht | CRITICAL |
| `shell_company` | Briefkastenfirmen-Verdacht | CRITICAL |
| `round_amount` | Verdächtig runde Beträge | LOW |
| `split_invoice` | Rechnungssplitting zur Umgehung von Limits | MEDIUM |
| `weekend_invoice` | Rechnungen an Wochenenden/Feiertagen | LOW |

---

## Risikostufen

| Stufe | Score-Bereich | Beschreibung |
|-------|---------------|--------------|
| `critical` | 85-100 | Sofortige Untersuchung erforderlich |
| `high` | 70-84 | Hohe Priorität zur Überprüfung |
| `medium` | 50-69 | Erhöhte Aufmerksamkeit empfohlen |
| `low` | 0-49 | Geringes Risiko, normale Bearbeitung |

---

## Endpunkte

### Analyse

#### GET /fraud/analyze

Analysiert ein Dokument auf Betrugsindikatoren.

**Query-Parameter**:
| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `document_id` | UUID | Ja | ID des zu analysierenden Dokuments |
| `deep_analysis` | bool | Nein | Erweiterte Analyse (default: false) |

**Response** (200):
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "risk_score": 72,
  "risk_level": "high",
  "findings": [
    {
      "type": "duplicate_invoice",
      "confidence": 0.89,
      "severity": "high",
      "description": "Rechnung mit ähnlichem Betrag und Datum gefunden",
      "related_documents": [
        {
          "id": "550e8400-e29b-41d4-a716-446655440001",
          "similarity": 0.95,
          "match_reason": "Betrag, Datum, Lieferant identisch"
        }
      ],
      "recommendation": "Manuelle Überprüfung empfohlen"
    },
    {
      "type": "price_anomaly",
      "confidence": 0.65,
      "severity": "medium",
      "description": "Preis liegt 45% über dem historischen Durchschnitt",
      "context": {
        "current_price": 1250.00,
        "average_price": 862.00,
        "deviation_percent": 45.0
      }
    }
  ],
  "entity_risk": {
    "entity_id": "550e8400-e29b-41d4-a716-446655440002",
    "entity_name_masked": "L***r GmbH",
    "overall_score": 68,
    "flags": ["new_supplier", "high_volume_sudden"]
  },
  "analyzed_at": "2026-01-27T14:30:00Z",
  "analysis_duration_ms": 1250
}
```

---

### Dashboard

#### GET /fraud/dashboard

Liefert aggregierte Fraud-Statistiken für das Dashboard.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `period` | string | Zeitraum: `day`, `week`, `month`, `quarter` (default: month) |

**Response** (200):
```json
{
  "period": "month",
  "period_start": "2026-01-01",
  "period_end": "2026-01-31",
  "summary": {
    "total_analyzed": 1250,
    "alerts_triggered": 47,
    "confirmed_fraud": 3,
    "false_positives": 12,
    "pending_review": 32
  },
  "risk_distribution": {
    "critical": 2,
    "high": 15,
    "medium": 20,
    "low": 10
  },
  "by_type": [
    {
      "type": "duplicate_invoice",
      "count": 18,
      "confirmed": 2
    },
    {
      "type": "price_anomaly",
      "count": 12,
      "confirmed": 0
    }
  ],
  "trend": {
    "direction": "decreasing",
    "change_percent": -15.5,
    "vs_previous_period": "Rückgang der Alerts um 15.5%"
  },
  "top_flagged_entities": [
    {
      "entity_id": "uuid-...",
      "name_masked": "M***r GmbH",
      "alert_count": 5,
      "highest_severity": "high"
    }
  ]
}
```

---

### Alerts

#### GET /fraud/alerts

Listet Fraud-Alerts auf.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Pagination Offset (default: 0) |
| `limit` | int | Anzahl Ergebnisse (default: 50, max: 100) |
| `status` | string | `new`, `investigating`, `confirmed`, `dismissed` |
| `risk_level` | string | `critical`, `high`, `medium`, `low` |
| `fraud_type` | string | Betrugstyp (siehe Tabelle oben) |
| `from_date` | date | Ab Datum (YYYY-MM-DD) |
| `to_date` | date | Bis Datum (YYYY-MM-DD) |

**Response** (200):
```json
{
  "alerts": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "fraud_type": "duplicate_invoice",
      "risk_level": "high",
      "risk_score": 78,
      "status": "new",
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "entity_id": "550e8400-e29b-41d4-a716-446655440002",
      "summary": "Mögliche Duplikat-Rechnung erkannt",
      "created_at": "2026-01-27T10:15:00Z",
      "assigned_to": null
    }
  ],
  "total": 47,
  "page": 1,
  "pages": 1
}
```

---

### Konfiguration

#### GET /fraud/config

Ruft die aktuelle Fraud-Detection-Konfiguration ab.

**Berechtigungen**: Admin erforderlich

**Response** (200):
```json
{
  "thresholds": {
    "duplicate_similarity": 0.85,
    "price_deviation_percent": 30.0,
    "new_supplier_volume_limit": 10000.00,
    "round_amount_threshold": 1000.00
  },
  "enabled_checks": [
    "duplicate_invoice",
    "price_anomaly",
    "phantom_supplier",
    "expense_fraud"
  ],
  "auto_alert": true,
  "auto_alert_threshold": 70,
  "notification_channels": ["email", "slack"],
  "review_workflow": {
    "auto_assign": true,
    "escalation_hours": 24
  }
}
```

---

#### PATCH /fraud/config

Aktualisiert die Fraud-Detection-Konfiguration.

**Berechtigungen**: Admin erforderlich

**Request Body**:
```json
{
  "thresholds": {
    "duplicate_similarity": 0.90,
    "price_deviation_percent": 25.0
  },
  "enabled_checks": [
    "duplicate_invoice",
    "price_anomaly",
    "phantom_supplier"
  ],
  "auto_alert_threshold": 65
}
```

**Response** (200): Aktualisierte Konfiguration

---

### Betrugstypen

#### GET /fraud/types

Listet alle verfügbaren Betrugstypen mit Beschreibungen.

**Response** (200):
```json
{
  "fraud_types": [
    {
      "id": "duplicate_invoice",
      "name": "Duplikat-Rechnung",
      "description": "Erkennt doppelt eingereichte Rechnungen basierend auf Betrag, Datum und Lieferant",
      "default_severity": "high",
      "configurable_threshold": true
    },
    {
      "id": "price_anomaly",
      "name": "Preisanomalie",
      "description": "Identifiziert ungewöhnliche Preisabweichungen vom historischen Durchschnitt",
      "default_severity": "medium",
      "configurable_threshold": true
    }
  ]
}
```

---

### Risikostufen

#### GET /fraud/risk-levels

Liefert die Definition der Risikostufen.

**Response** (200):
```json
{
  "risk_levels": [
    {
      "level": "critical",
      "score_min": 85,
      "score_max": 100,
      "color": "#dc2626",
      "description": "Sofortige Untersuchung erforderlich",
      "sla_hours": 4
    },
    {
      "level": "high",
      "score_min": 70,
      "score_max": 84,
      "color": "#f59e0b",
      "description": "Hohe Priorität zur Überprüfung",
      "sla_hours": 24
    }
  ]
}
```

---

### Entity-Risikoprofil

#### GET /fraud/entity/{entity_id}/risk-profile

Ruft das Risikoprofil eines Geschäftspartners ab.

**Response** (200):
```json
{
  "entity_id": "550e8400-e29b-41d4-a716-446655440002",
  "current_risk_score": 68,
  "risk_level": "medium",
  "flags": [
    {
      "flag": "new_supplier",
      "since": "2026-01-15",
      "description": "Neuer Lieferant (< 90 Tage)"
    },
    {
      "flag": "high_volume_sudden",
      "since": "2026-01-20",
      "description": "Plötzlicher Volumenanstieg (+200%)"
    }
  ],
  "history": [
    {
      "date": "2026-01-27",
      "score": 68,
      "change": "+12"
    },
    {
      "date": "2026-01-20",
      "score": 56,
      "change": "+8"
    }
  ],
  "related_alerts": [
    {
      "id": "alert-uuid",
      "type": "price_anomaly",
      "date": "2026-01-25",
      "status": "investigating"
    }
  ],
  "recommendation": "Erhöhte Überwachung empfohlen. Transaktionen manuell prüfen."
}
```

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `FRAUD_DOCUMENT_NOT_FOUND` | 404 | Dokument nicht gefunden |
| `FRAUD_ENTITY_NOT_FOUND` | 404 | Geschäftspartner nicht gefunden |
| `FRAUD_ANALYSIS_FAILED` | 500 | Analyse fehlgeschlagen |
| `FRAUD_CONFIG_INVALID` | 422 | Ungültige Konfiguration |
| `FRAUD_ALERT_NOT_FOUND` | 404 | Alert nicht gefunden |

---

## Alert-Workflow

```
┌─────────┐     ┌──────────────┐     ┌───────────┐
│   NEW   │ ──► │ INVESTIGATING│ ──► │ CONFIRMED │
└─────────┘     └──────────────┘     └───────────┘
     │                │
     │                ▼
     │          ┌───────────┐
     └────────► │ DISMISSED │
                └───────────┘
```

**Status-Beschreibungen**:
- `new`: Neuer Alert, nicht zugewiesen
- `investigating`: In Bearbeitung durch Mitarbeiter
- `confirmed`: Als Betrug bestätigt
- `dismissed`: Als False Positive markiert

---

## Sicherheitshinweise

1. **PII-Schutz**: Entity-Namen werden maskiert (L***r GmbH)
2. **Audit-Trail**: Alle Zugriffe werden protokolliert
3. **Multi-Tenant**: Strikte Company-Isolation
4. **Rate Limiting**: Max. 100 Analyse-Anfragen/Minute
5. **Zugriffsrechte**: Nur autorisierte Benutzer

---

## Celery Tasks

| Task | Schedule | Beschreibung |
|------|----------|--------------|
| `fraud.scan_new_documents` | Alle 5 Min | Scannt neue Dokumente |
| `fraud.recalculate_entity_scores` | Täglich 03:00 | Aktualisiert Entity-Scores |
| `fraud.escalate_overdue_alerts` | Stündlich | Eskaliert überfällige Alerts |
| `fraud.generate_daily_report` | Täglich 08:00 | Generiert Tagesbericht |

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
