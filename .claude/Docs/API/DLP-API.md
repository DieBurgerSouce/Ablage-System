# DLP (Data Loss Prevention) API

## Übersicht

Die DLP-API ermöglicht policy-basierte Zugriffskontrollen für Dokumente. Sie schützt sensible Daten durch Download-Restriktionen, automatische Wasserzeichen und Erkennung sensibler Informationen.

**Basis-URL**: `/api/v1/dlp`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt

---

## Endpunkte

### Policies

#### GET /dlp/policies

Listet alle DLP-Policies der aktuellen Company auf.

**Berechtigungen**: Admin erforderlich

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Pagination Offset (default: 0) |
| `limit` | int | Anzahl Ergebnisse (default: 100, max: 100) |
| `enabled_only` | bool | Nur aktive Policies (default: false) |

**Response** (200):
```json
{
  "policies": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Vertrauliche Dokumente",
      "description": "Schutz für vertrauliche Unternehmensdokumente",
      "enabled": true,
      "priority": 10,
      "conditions": {
        "tags": ["vertraulich", "intern"],
        "document_types": ["contract", "financial"],
        "roles_denied": ["guest", "external"]
      },
      "actions": {
        "action": "watermark",
        "watermark_text": "VERTRAULICH - {user_email}",
        "notify_admin": true
      },
      "created_at": "2026-01-15T10:00:00Z",
      "updated_at": "2026-01-15T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

#### POST /dlp/policies

Erstellt eine neue DLP-Policy.

**Berechtigungen**: Admin erforderlich

**Request Body**:
```json
{
  "name": "Finanzberichte Schutz",
  "description": "Verhindert Download von Finanzberichten durch Externe",
  "enabled": true,
  "priority": 5,
  "conditions": {
    "tags": ["finanzbericht", "jahresabschluss"],
    "document_types": ["financial_report"],
    "roles_denied": ["external", "guest"],
    "time_restrictions": {
      "denied_hours": [0, 6],
      "denied_days": ["saturday", "sunday"]
    }
  },
  "actions": {
    "action": "block",
    "message": "Download von Finanzberichten ist für externe Benutzer nicht gestattet.",
    "notify_admin": true,
    "log_access": true
  }
}
```

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "name": "Finanzberichte Schutz",
  "enabled": true,
  "created_at": "2026-01-20T14:30:00Z"
}
```

---

#### GET /dlp/policies/{policy_id}

Ruft eine einzelne Policy ab.

**Berechtigungen**: Admin erforderlich

**Response** (200): Vollständiges Policy-Objekt

**Fehler**:
- `404`: Policy nicht gefunden

---

#### PATCH /dlp/policies/{policy_id}

Aktualisiert eine bestehende Policy.

**Berechtigungen**: Admin erforderlich

**Request Body** (alle Felder optional):
```json
{
  "name": "Aktualisierter Name",
  "enabled": false,
  "priority": 20,
  "conditions": { ... },
  "actions": { ... }
}
```

**Response** (200): Aktualisiertes Policy-Objekt

---

#### DELETE /dlp/policies/{policy_id}

Löscht eine Policy.

**Berechtigungen**: Admin erforderlich

**Response** (204): Kein Inhalt

---

### Zugriffsprüfung

#### POST /dlp/check

Prüft, ob ein Dokumentzugriff erlaubt ist.

**Request Body**:
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440002",
  "access_type": "download",
  "user_context": {
    "roles": ["employee"],
    "department": "accounting"
  }
}
```

**Access Types**:
- `view` - Dokument anzeigen
- `download` - Dokument herunterladen
- `print` - Dokument drucken
- `share` - Dokument teilen
- `export` - Dokument exportieren

**Response** (200):
```json
{
  "allowed": true,
  "action": "watermark",
  "watermark_config": {
    "text": "VERTRAULICH - max.mustermann@firma.de",
    "position": "diagonal",
    "opacity": 0.3,
    "font_size": 48
  },
  "matched_policy": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Vertrauliche Dokumente"
  },
  "audit_id": "audit_abc123"
}
```

**Wenn blockiert**:
```json
{
  "allowed": false,
  "action": "block",
  "reason": "Download von Finanzberichten ist für externe Benutzer nicht gestattet.",
  "matched_policy": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Finanzberichte Schutz"
  }
}
```

---

### Sensitive Data Scan

#### POST /dlp/scan

Scannt Text auf sensible Daten.

**Request Body**:
```json
{
  "text": "Bitte überweisen Sie auf IBAN DE89370400440532013000. Meine Kreditkarte ist 4111111111111111.",
  "data_types": ["credit_card", "iban", "email", "phone"]
}
```

**Verfügbare Datentypen**:
| Typ | Beschreibung | Beispiel |
|-----|--------------|----------|
| `credit_card` | Kreditkartennummern (Luhn) | 4111111111111111 |
| `iban` | IBAN (DE-Format) | DE89370400440532013000 |
| `ssn` | US Social Security Number | 123-45-6789 |
| `tax_id` | Steuer-IDs | DE123456789 |
| `email` | E-Mail-Adressen | max@firma.de |
| `phone` | Telefonnummern | +49 30 12345678 |
| `date_of_birth` | Geburtsdaten | 01.01.1980 |

**Response** (200):
```json
{
  "findings": [
    {
      "type": "iban",
      "value_masked": "DE89***********3000",
      "position": {
        "start": 31,
        "end": 53
      },
      "confidence": 0.99
    },
    {
      "type": "credit_card",
      "value_masked": "4111********1111",
      "position": {
        "start": 76,
        "end": 92
      },
      "confidence": 0.95
    }
  ],
  "risk_level": "high",
  "recommendation": "Dokument enthält sensible Finanzdaten. Zugriff einschränken empfohlen."
}
```

---

#### GET /dlp/sensitive-data-types

Listet alle verfügbaren Datentypen für den Scan.

**Response** (200):
```json
{
  "data_types": [
    {
      "id": "credit_card",
      "name": "Kreditkarte",
      "description": "Kreditkartennummern mit Luhn-Validierung",
      "severity": "high"
    },
    {
      "id": "iban",
      "name": "IBAN",
      "description": "Internationale Bankkontonummern (DE-Format)",
      "severity": "high"
    }
  ]
}
```

---

## DLP Actions

| Action | Beschreibung |
|--------|--------------|
| `allow` | Zugriff erlauben ohne Einschränkungen |
| `block` | Zugriff vollständig blockieren |
| `watermark` | Zugriff mit Wasserzeichen erlauben |
| `notify` | Erlauben und Admin benachrichtigen |
| `audit_only` | Nur protokollieren, keine Einschränkung |

---

## Policy Conditions

### Tag-basierte Bedingungen
```json
{
  "tags": ["vertraulich", "intern"],
  "tags_match": "any"  // "any" oder "all"
}
```

### Rollen-basierte Bedingungen
```json
{
  "roles_allowed": ["admin", "manager"],
  "roles_denied": ["guest", "external"]
}
```

### Zeit-basierte Bedingungen
```json
{
  "time_restrictions": {
    "allowed_hours": [9, 18],
    "allowed_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "timezone": "Europe/Berlin"
  }
}
```

### Dokumenttyp-Bedingungen
```json
{
  "document_types": ["invoice", "contract", "financial_report"]
}
```

---

## Wasserzeichen-Konfiguration

```json
{
  "watermark_text": "VERTRAULICH - {user_email} - {date}",
  "position": "diagonal",
  "opacity": 0.3,
  "font_size": 48,
  "color": "#808080"
}
```

**Verfügbare Platzhalter**:
- `{user_email}` - E-Mail des zugreifenden Benutzers
- `{user_name}` - Name des Benutzers
- `{date}` - Aktuelles Datum
- `{time}` - Aktuelle Uhrzeit
- `{document_id}` - Dokument-ID

**Positionen**:
- `diagonal` - Diagonal über das Dokument
- `center` - Zentriert
- `top` - Oberer Rand
- `bottom` - Unterer Rand
- `tile` - Gekachelt über gesamtes Dokument

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `DLP_POLICY_NOT_FOUND` | 404 | Policy nicht gefunden |
| `DLP_POLICY_EXISTS` | 409 | Policy-Name existiert bereits |
| `DLP_ACCESS_DENIED` | 403 | Zugriff durch DLP-Policy verweigert |
| `DLP_SCAN_FAILED` | 500 | Scan fehlgeschlagen |
| `DLP_INVALID_CONDITIONS` | 422 | Ungültige Policy-Bedingungen |

---

## Sicherheitshinweise

1. **Admin-Only**: Policy-Verwaltung nur für Administratoren
2. **Audit-Trail**: Alle Zugriffsprüfungen werden protokolliert
3. **Multi-Tenant**: Policies sind company-isoliert
4. **Keine PII in Logs**: Sensible Daten werden maskiert geloggt
5. **Fail-Closed**: Bei Fehlern wird Zugriff standardmäßig verweigert

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
