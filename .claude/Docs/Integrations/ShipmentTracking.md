# Shipment Tracking Integration

> **Letzte Aktualisierung**: 2026-01-27
> **Status**: Production-Ready
> **Migration**: 100 (add_shipment_tracking)

---

## Übersicht

Die Shipment Tracking Integration ermöglicht die automatische Verfolgung von Paketsendungen über alle großen deutschen und internationalen Paketdienste. Der Service erkennt automatisch den Carrier anhand der Tracking-Nummer und bietet eine einheitliche API für Status-Abfragen.

**Basis-URL**: `/api/v1/shipments`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt (RLS)

---

## Unterstützte Carrier

| Carrier | Code | Pattern | API |
|---------|------|---------|-----|
| DHL | `dhl` | `00340...`, `JJD...` | DHL Geschäftskundenportal |
| DPD | `dpd` | 14-stellig, `01...` | DPD myDPD Business |
| Hermes | `hermes` | `H...` Prefix | Hermes ProfiPaketService |
| UPS | `ups` | `1Z...` (18 Zeichen) | UPS Developer Kit (OAuth2) |
| GLS | `gls` | 11-stellig | GLS Web API |
| FedEx | `fedex` | 12/15/20-stellig | FedEx Web Services (OAuth2) |
| Deutsche Post | `deutsche_post` | `RR...DE`, `LX...` | Brief-API via DHL |

---

## Sendungsstatus

| Status | Beschreibung |
|--------|--------------|
| `pending` | Sendung angelegt, noch nicht abgeholt |
| `in_transit` | Unterwegs |
| `out_for_delivery` | In Zustellung |
| `delivered` | Zugestellt |
| `exception` | Problem (beschädigt, verzögert) |
| `returned` | Zurückgesendet |
| `unknown` | Status nicht ermittelbar |

---

## Sendungsrichtung

| Richtung | Code | Beschreibung |
|----------|------|--------------|
| Eingehend | `inbound` | Wareneingang von Lieferanten |
| Ausgehend | `outbound` | Versand an Kunden |
| Retoure | `return` | Rücksendung |

---

## Core Services

| Service | Datei | Zweck |
|---------|-------|-------|
| **CarrierService** | `shipping/carrier_service.py` | Zentrale Sendungsverwaltung |
| **CarrierProviders** | `shipping/carrier_providers.py` | Carrier-spezifische API-Anbindung |

---

## Endpunkte

### Sendungen verwalten

#### POST /shipments

Erstellt eine neue Sendung zur Verfolgung.

**Request Body**:
```json
{
  "tracking_number": "00340434173456789012",
  "carrier": "dhl",
  "direction": "inbound",
  "entity_id": "550e8400-e29b-41d4-a716-446655440000",
  "document_id": "550e8400-e29b-41d4-a716-446655440001",
  "expected_delivery": "2026-01-30",
  "description": "Büromaterial von Müller Office"
}
```

**Carrier Auto-Detection**: Wenn `carrier` nicht angegeben wird, erfolgt automatische Erkennung anhand der Tracking-Nummer.

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "tracking_number": "00340434173456789012",
  "carrier": "dhl",
  "status": "pending",
  "direction": "inbound",
  "entity": {
    "id": "...",
    "name_masked": "M***r Office GmbH"
  },
  "created_at": "2026-01-27T10:00:00Z"
}
```

---

#### GET /shipments

Listet Sendungen mit Filterung und Paginierung.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Pagination Offset (default: 0) |
| `limit` | int | Anzahl Ergebnisse (default: 50, max: 100) |
| `status` | string | Statusfilter (kommasepariert) |
| `carrier` | string | Carrierfilter (kommasepariert) |
| `direction` | string | Richtungsfilter |
| `entity_id` | UUID | Sendungen für Geschäftspartner |
| `from_date` | date | Ab Datum |
| `to_date` | date | Bis Datum |
| `search` | string | Suche in Tracking-Nummer/Beschreibung |

**Response** (200):
```json
{
  "shipments": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440010",
      "tracking_number": "00340434173456789012",
      "carrier": "dhl",
      "status": "in_transit",
      "direction": "inbound",
      "last_event": {
        "timestamp": "2026-01-27T08:30:00Z",
        "description": "Sendung im Ziel-Paketzentrum",
        "location": "Nürnberg"
      },
      "expected_delivery": "2026-01-28",
      "entity": {
        "id": "...",
        "name_masked": "M***r Office GmbH"
      }
    }
  ],
  "total": 45,
  "page": 1,
  "pages": 1
}
```

---

#### GET /shipments/{shipment_id}

Ruft Details einer Sendung mit vollständiger Event-Historie ab.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "tracking_number": "00340434173456789012",
  "carrier": "dhl",
  "carrier_name": "DHL",
  "status": "in_transit",
  "direction": "inbound",
  "entity": {
    "id": "...",
    "name": "Müller Office GmbH"
  },
  "document": {
    "id": "...",
    "filename": "Lieferschein_2026-001.pdf"
  },
  "description": "Büromaterial von Müller Office",
  "weight_kg": 5.2,
  "expected_delivery": "2026-01-28",
  "actual_delivery": null,
  "events": [
    {
      "timestamp": "2026-01-27T08:30:00Z",
      "status": "in_transit",
      "description": "Sendung im Ziel-Paketzentrum",
      "location": "Nürnberg",
      "raw_status": "DE-HUB-01"
    },
    {
      "timestamp": "2026-01-26T14:00:00Z",
      "status": "in_transit",
      "description": "Sendung in Bearbeitung",
      "location": "Frankfurt",
      "raw_status": "DE-HUB-02"
    },
    {
      "timestamp": "2026-01-26T10:00:00Z",
      "status": "pending",
      "description": "Sendung abgeholt",
      "location": "München",
      "raw_status": "PICKUP"
    }
  ],
  "tracking_url": "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode=00340434173456789012",
  "created_at": "2026-01-26T09:00:00Z",
  "updated_at": "2026-01-27T08:30:00Z"
}
```

---

#### POST /shipments/{shipment_id}/refresh

Aktualisiert den Status einer Sendung vom Carrier.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "status": "out_for_delivery",
  "status_changed": true,
  "new_events": [
    {
      "timestamp": "2026-01-28T07:00:00Z",
      "description": "Sendung in Zustellung",
      "location": "Erlangen"
    }
  ],
  "refreshed_at": "2026-01-28T07:05:00Z"
}
```

---

### Carrier-Erkennung

#### GET /shipments/detect-carrier

Erkennt den Carrier anhand einer Tracking-Nummer.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `tracking_number` | string | Die zu prüfende Tracking-Nummer |

**Response** (200):
```json
{
  "tracking_number": "00340434173456789012",
  "detected_carrier": "dhl",
  "carrier_name": "DHL",
  "confidence": 0.99,
  "patterns_matched": ["^00340[0-9]{17}$"]
}
```

**Bei unbekanntem Carrier**:
```json
{
  "tracking_number": "UNKNOWN123",
  "detected_carrier": "unknown",
  "carrier_name": null,
  "confidence": 0.0,
  "patterns_matched": []
}
```

---

### Statistiken

#### GET /shipments/summary

Zusammenfassung aller Sendungen.

**Response** (200):
```json
{
  "total": 156,
  "by_carrier": {
    "dhl": 78,
    "dpd": 45,
    "hermes": 20,
    "ups": 8,
    "gls": 5
  },
  "by_status": {
    "delivered": 120,
    "in_transit": 25,
    "out_for_delivery": 5,
    "pending": 3,
    "exception": 2,
    "returned": 1
  },
  "pending_delivery": 33,
  "delivered_today": 8,
  "exceptions": 2
}
```

---

#### GET /shipments/statistics

Detaillierte Statistiken pro Carrier.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `period` | string | `week`, `month`, `quarter` (default: month) |

**Response** (200):
```json
{
  "period": "month",
  "carriers": [
    {
      "carrier": "dhl",
      "total_shipments": 78,
      "delivered": 72,
      "avg_delivery_days": 1.8,
      "on_time_rate": 0.94,
      "exception_rate": 0.02
    },
    {
      "carrier": "dpd",
      "total_shipments": 45,
      "delivered": 42,
      "avg_delivery_days": 2.1,
      "on_time_rate": 0.89,
      "exception_rate": 0.04
    }
  ],
  "overall": {
    "total_shipments": 156,
    "avg_delivery_days": 1.9,
    "on_time_rate": 0.91
  }
}
```

---

## Celery Tasks

| Task | Schedule | Queue | Beschreibung |
|------|----------|-------|--------------|
| `shipment_tracking.refresh_active` | Stündlich (:15) | default | Aktive Sendungen aktualisieren |
| `shipment_tracking.check_delayed` | Täglich 09:00 | maintenance | Verspätungen prüfen & Alert erstellen |
| `shipment_tracking.cleanup_old` | Wöchentlich | maintenance | Alte Sendungsdaten archivieren |

---

## Konfiguration

**Umgebungsvariablen** (optional, Mock wenn nicht gesetzt):

```python
# DHL Geschäftskundenportal
DHL_API_KEY: SecretStr

# DPD myDPD Business
DPD_API_USER: str
DPD_API_PASSWORD: SecretStr

# UPS Developer Kit (OAuth2)
UPS_CLIENT_ID: str
UPS_CLIENT_SECRET: SecretStr

# GLS Web API
GLS_API_USER: str
GLS_API_PASSWORD: SecretStr

# FedEx Web Services (OAuth2)
FEDEX_CLIENT_ID: str
FEDEX_CLIENT_SECRET: SecretStr

# Hermes ProfiPaketService
HERMES_API_KEY: SecretStr
```

**Fallback-Modus**: Ohne API-Credentials arbeitet der Service im Mock-Modus und liefert simulierte Tracking-Daten für Entwicklung/Testing.

---

## Tracking-Nummer-Pattern

| Carrier | Pattern | Beispiel |
|---------|---------|----------|
| DHL | `^00340[0-9]{17}$` oder `^JJD[0-9]{18}$` | `00340434173456789012` |
| DPD | `^[0-9]{14}$` oder `^01[0-9]{12}$` | `01234567890123` |
| Hermes | `^H[0-9]{19}$` | `H1234567890123456789` |
| UPS | `^1Z[A-Z0-9]{16}$` | `1Z999AA10123456784` |
| GLS | `^[0-9]{11}$` | `12345678901` |
| FedEx | `^[0-9]{12,15,20}$` | `123456789012` |
| Deutsche Post | `^RR[0-9]{9}DE$` oder `^LX[0-9]{9}[A-Z]{2}$` | `RR123456789DE` |

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `SHIP_NOT_FOUND` | 404 | Sendung nicht gefunden |
| `SHIP_CARRIER_UNKNOWN` | 400 | Carrier konnte nicht erkannt werden |
| `SHIP_TRACKING_FAILED` | 502 | Carrier-API nicht erreichbar |
| `SHIP_INVALID_NUMBER` | 422 | Ungültige Tracking-Nummer |

---

## Sicherheitshinweise

1. **Input-Validierung**: Tracking-Nummern werden gegen ReDoS-sichere Patterns validiert (CWE-20)
2. **URL-Encoding**: Tracking-Nummern werden vor API-Aufrufen URL-encoded (CWE-116)
3. **Multi-Tenant**: Strikte Company-Isolation via RLS Policies
4. **API-Credentials**: Alle Carrier-API-Keys als SecretStr verschlüsselt
5. **PII-Schutz**: Entity-Namen werden in Listen maskiert

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
