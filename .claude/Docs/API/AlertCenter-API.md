# Alert Center API

## Übersicht

Das Alert Center ist die zentrale Stelle für alle System-Benachrichtigungen. Es kategorisiert, priorisiert und verfolgt Alerts aus verschiedenen Quellen wie Fraud Detection, Risiko-Monitoring, Compliance-Checks und System-Überwachung.

**Basis-URL**: `/api/v1/alerts`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt

---

## Alert-Kategorien

| Kategorie | Code-Prefix | Beschreibung |
|-----------|-------------|--------------|
| `fraud` | FRAUD_* | Betrugsverdacht (Duplikate, Preisanomalien) |
| `risk` | RISK_* | Risikowarnungen (High-Risk Entities) |
| `compliance` | COMP_* | Compliance-Verletzungen (GDPR, GoBD, DLP) |
| `deadline` | DEAD_* | Fristwarnungen (Skonto, Rechnungen) |
| `system` | SYS_* | Systemwarnungen (GPU, Disk, OCR-Fehlerrate) |
| `security` | SEC_* | Sicherheitswarnungen (Login-Versuche) |
| `quality` | QUAL_* | Qualitätswarnungen (OCR-Confidence) |
| `workflow` | WORK_* | Workflow-Alerts (Eskalation, Delegation) |

---

## Schweregrade

| Schweregrad | Farbe | Beschreibung |
|-------------|-------|--------------|
| `critical` | Rot | Sofortige Aktion erforderlich |
| `high` | Orange | Hohe Priorität, zeitnah bearbeiten |
| `medium` | Gelb | Mittlere Priorität |
| `low` | Blau | Niedrige Priorität |
| `info` | Grau | Informativ, keine Aktion erforderlich |

---

## Alert-Status

```
┌───────┐     ┌──────────────┐     ┌───────────┐
│  NEW  │ ──► │ ACKNOWLEDGED │ ──► │ RESOLVED  │
└───────┘     └──────────────┘     └───────────┘
    │              │                     │
    │              ▼                     │
    │        ┌───────────┐               │
    │        │IN_PROGRESS│               │
    │        └───────────┘               │
    │              │                     │
    ▼              ▼                     ▼
┌───────────┐ ┌───────────┐       ┌───────────┐
│ DISMISSED │ │ ESCALATED │       │  EXPIRED  │
└───────────┘ └───────────┘       └───────────┘
```

---

## Endpunkte

### Liste & Filterung

#### GET /alerts

Listet Alerts mit umfangreichen Filtermöglichkeiten.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Pagination Offset (default: 0) |
| `limit` | int | Anzahl Ergebnisse (default: 50, max: 100) |
| `category` | string | Kategorie-Filter (kommasepariert) |
| `severity` | string | Schweregrad-Filter (kommasepariert) |
| `status` | string | Status-Filter (kommasepariert) |
| `from_date` | datetime | Ab Datum (ISO 8601) |
| `to_date` | datetime | Bis Datum (ISO 8601) |
| `assigned_to` | UUID | Zugewiesener Benutzer |
| `unassigned` | bool | Nur nicht zugewiesene Alerts |
| `document_id` | UUID | Alerts für spezifisches Dokument |
| `entity_id` | UUID | Alerts für spezifischen Geschäftspartner |
| `search` | string | Volltextsuche in Titel/Nachricht |
| `sort_by` | string | Sortierung: `created_at`, `severity`, `category` |
| `sort_order` | string | `asc` oder `desc` (default: desc) |

**Response** (200):
```json
{
  "alerts": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "alert_code": "FRAUD_001",
      "title": "Mögliche Duplikat-Rechnung erkannt",
      "message": "Rechnung RE-2026-001234 ähnelt RE-2026-001200 zu 95%",
      "category": "fraud",
      "severity": "high",
      "status": "new",
      "document_id": "550e8400-e29b-41d4-a716-446655440001",
      "entity_id": "550e8400-e29b-41d4-a716-446655440002",
      "assigned_to_id": null,
      "created_at": "2026-01-27T10:15:00Z",
      "updated_at": "2026-01-27T10:15:00Z",
      "metadata": {
        "similarity_score": 0.95,
        "related_document_id": "550e8400-e29b-41d4-a716-446655440003"
      },
      "context": {
        "source_page": "/documents/550e8400-e29b-41d4-a716-446655440001"
      }
    }
  ],
  "total": 47,
  "page": 1,
  "pages": 1,
  "filters_applied": {
    "category": null,
    "severity": null,
    "status": null
  }
}
```

---

### Statistiken

#### GET /alerts/stats

Dashboard-Statistiken für Alert-Übersicht.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `period` | string | `day`, `week`, `month` (default: week) |

**Response** (200):
```json
{
  "summary": {
    "total": 156,
    "new": 23,
    "acknowledged": 45,
    "in_progress": 18,
    "resolved": 62,
    "dismissed": 8
  },
  "by_severity": {
    "critical": 3,
    "high": 15,
    "medium": 28,
    "low": 67,
    "info": 43
  },
  "by_category": {
    "fraud": 18,
    "risk": 25,
    "compliance": 12,
    "deadline": 45,
    "system": 8,
    "security": 5,
    "quality": 28,
    "workflow": 15
  },
  "last_24h": {
    "new": 12,
    "resolved": 8,
    "critical_unresolved": 1
  },
  "trend": {
    "vs_previous_period": -15,
    "direction": "decreasing"
  },
  "avg_resolution_time_hours": 4.5
}
```

---

#### GET /alerts/counts

Schnelle Zähler für Navigation-Badges.

**Response** (200):
```json
{
  "total_unresolved": 86,
  "new": 23,
  "critical": 3,
  "high": 15,
  "my_alerts": 7
}
```

---

### CRUD-Operationen

#### GET /alerts/{alert_id}

Ruft einen einzelnen Alert ab.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "alert_code": "FRAUD_001",
  "title": "Mögliche Duplikat-Rechnung erkannt",
  "message": "Detaillierte Beschreibung...",
  "category": "fraud",
  "severity": "high",
  "status": "acknowledged",
  "document_id": "...",
  "entity_id": "...",
  "assigned_to_id": "550e8400-e29b-41d4-a716-446655440005",
  "assigned_to": {
    "id": "...",
    "name": "Max Mustermann",
    "email": "max@firma.de"
  },
  "created_at": "2026-01-27T10:15:00Z",
  "acknowledged_at": "2026-01-27T10:30:00Z",
  "resolved_at": null,
  "metadata": { ... },
  "context": { ... },
  "history": [
    {
      "action": "created",
      "timestamp": "2026-01-27T10:15:00Z",
      "user_id": null,
      "details": "Alert automatisch erstellt"
    },
    {
      "action": "acknowledged",
      "timestamp": "2026-01-27T10:30:00Z",
      "user_id": "...",
      "details": "Zur Kenntnis genommen von Max Mustermann"
    }
  ]
}
```

---

#### POST /alerts

Erstellt einen manuellen Alert.

**Request Body**:
```json
{
  "title": "Manuelle Warnung",
  "message": "Beschreibung der Warnung",
  "category": "workflow",
  "severity": "medium",
  "document_id": "550e8400-e29b-41d4-a716-446655440001",
  "entity_id": null,
  "metadata": {
    "custom_field": "value"
  }
}
```

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "alert_code": "WORK_MANUAL_001",
  "status": "new",
  "created_at": "2026-01-27T14:00:00Z"
}
```

---

### Status-Aktionen

#### POST /alerts/{alert_id}/acknowledge

Markiert Alert als zur Kenntnis genommen.

**Request Body** (optional):
```json
{
  "comment": "Wird geprüft"
}
```

**Response** (200):
```json
{
  "id": "...",
  "status": "acknowledged",
  "acknowledged_at": "2026-01-27T14:05:00Z",
  "acknowledged_by": "Max Mustermann"
}
```

---

#### POST /alerts/{alert_id}/dismiss

Verwirft einen Alert (False Positive).

**Request Body**:
```json
{
  "reason": "false_positive",
  "comment": "Kein echtes Duplikat - unterschiedliche Leistungszeiträume"
}
```

**Dismiss Reasons**:
- `false_positive` - Falsch-Positiv
- `duplicate` - Duplikat-Alert
- `not_relevant` - Nicht relevant
- `resolved_externally` - Extern gelöst
- `other` - Sonstiges (Kommentar erforderlich)

**Response** (200):
```json
{
  "id": "...",
  "status": "dismissed",
  "dismissed_at": "2026-01-27T14:10:00Z",
  "dismissed_by": "Max Mustermann",
  "dismiss_reason": "false_positive"
}
```

---

#### POST /alerts/{alert_id}/resolve

Markiert Alert als gelöst.

**Request Body**:
```json
{
  "resolution": "Rechnung storniert und Lieferant informiert",
  "action_taken": "invoice_cancelled"
}
```

**Response** (200):
```json
{
  "id": "...",
  "status": "resolved",
  "resolved_at": "2026-01-27T14:15:00Z",
  "resolved_by": "Max Mustermann"
}
```

---

#### POST /alerts/{alert_id}/escalate

Eskaliert Alert an anderen Benutzer oder höhere Ebene.

**Request Body**:
```json
{
  "escalate_to_user_id": "550e8400-e29b-41d4-a716-446655440020",
  "reason": "Benötigt Management-Entscheidung",
  "priority_boost": true
}
```

**Response** (200):
```json
{
  "id": "...",
  "status": "escalated",
  "severity": "critical",
  "assigned_to_id": "550e8400-e29b-41d4-a716-446655440020",
  "escalated_at": "2026-01-27T14:20:00Z"
}
```

---

#### POST /alerts/{alert_id}/assign

Weist Alert einem Benutzer zu.

**Request Body**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440025",
  "comment": "Bitte prüfen"
}
```

**Response** (200):
```json
{
  "id": "...",
  "assigned_to_id": "550e8400-e29b-41d4-a716-446655440025",
  "assigned_at": "2026-01-27T14:25:00Z"
}
```

---

### Massenaktionen

#### POST /alerts/bulk

Führt Aktionen auf mehrere Alerts gleichzeitig aus.

**Request Body**:
```json
{
  "alert_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ],
  "action": "acknowledge",
  "comment": "Massenbearbeitung"
}
```

**Verfügbare Actions**:
- `acknowledge` - Alle zur Kenntnis nehmen
- `dismiss` - Alle verwerfen (reason erforderlich)
- `assign` - Alle zuweisen (user_id erforderlich)
- `resolve` - Alle lösen

**Response** (200):
```json
{
  "processed": 3,
  "success": 3,
  "failed": 0,
  "results": [
    {
      "id": "...",
      "status": "success"
    }
  ]
}
```

---

## Alert-Codes

### Fraud (FRAUD_*)

| Code | Beschreibung |
|------|--------------|
| FRAUD_001 | Duplikat-Rechnung erkannt |
| FRAUD_002 | Preisanomalie festgestellt |
| FRAUD_003 | Verdächtiger Lieferant |
| FRAUD_004 | Spesen-Anomalie |

### Risk (RISK_*)

| Code | Beschreibung |
|------|--------------|
| RISK_001 | High-Risk Entity erkannt |
| RISK_002 | Zahlungsverzögerung kritisch |
| RISK_003 | Kreditlimit überschritten |
| RISK_004 | Ungewöhnliches Transaktionsmuster |

### Compliance (COMP_*)

| Code | Beschreibung |
|------|--------------|
| COMP_001 | GDPR-Löschfrist erreicht |
| COMP_002 | Aufbewahrungsfrist abgelaufen |
| COMP_003 | DLP-Policy-Verletzung |
| COMP_004 | Audit-Log-Anomalie |
| COMP_005 | Fehlende Pflichtangaben |

### Deadline (DEAD_*)

| Code | Beschreibung |
|------|--------------|
| DEAD_001 | Skonto-Frist läuft ab |
| DEAD_002 | Zahlungsziel erreicht |
| DEAD_003 | Vertragsverlängerung fällig |
| DEAD_004 | Dokumentprüfung überfällig |

### System (SYS_*)

| Code | Beschreibung |
|------|--------------|
| SYS_001 | GPU-Speicher kritisch |
| SYS_002 | Festplattenplatz niedrig |
| SYS_003 | Hohe OCR-Fehlerrate |
| SYS_004 | Worker-Queue überlastet |
| SYS_005 | Datenbank-Performance degradiert |

### Security (SEC_*)

| Code | Beschreibung |
|------|--------------|
| SEC_001 | Mehrfache fehlgeschlagene Logins |
| SEC_002 | Ungewöhnliche API-Nutzung |
| SEC_003 | Verdächtige IP-Adresse |
| SEC_004 | Berechtigungsänderung |

### Quality (QUAL_*)

| Code | Beschreibung |
|------|--------------|
| QUAL_001 | Niedrige OCR-Confidence |
| QUAL_002 | Umlaut-Erkennungsproblem |
| QUAL_003 | Dokumentqualität unzureichend |

### Workflow (WORK_*)

| Code | Beschreibung |
|------|--------------|
| WORK_001 | Genehmigung ausstehend |
| WORK_002 | Eskalation erforderlich |
| WORK_003 | Delegation abgelehnt |

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `ALERT_NOT_FOUND` | 404 | Alert nicht gefunden |
| `ALERT_ALREADY_RESOLVED` | 409 | Alert bereits gelöst |
| `ALERT_INVALID_TRANSITION` | 422 | Ungültiger Statusübergang |
| `ALERT_BULK_PARTIAL_FAILURE` | 207 | Teilweise fehlgeschlagen |

---

## Sicherheitshinweise

1. **Multi-Tenant**: Strikte Company-Isolation via RLS
2. **Audit-Trail**: Alle Aktionen werden protokolliert
3. **Berechtigungen**: Statusänderungen nur für autorisierte Benutzer
4. **PII-Schutz**: Sensible Daten in metadata maskiert

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
