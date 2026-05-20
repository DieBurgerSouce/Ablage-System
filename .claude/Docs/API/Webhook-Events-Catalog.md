# Webhook-Events-Katalog

> **Ablage-System - Vollständiger Event-Referenz für Webhooks**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Webhooks ermöglichen Echtzeit-Benachrichtigungen über Ereignisse im Ablage-System. Dieses Dokument beschreibt alle verfügbaren Events, Payload-Strukturen und Best Practices.

**Base URL:** `https://ablage.ihre-firma.de`
**Webhook Version:** `v1`
**Signatur-Algorithmus:** HMAC-SHA256

---

## Inhaltsverzeichnis

1. [Webhook-Konfiguration](#webhook-konfiguration)
2. [Event-Kategorien](#event-kategorien)
3. [Document Events](#document-events)
4. [OCR Events](#ocr-events)
5. [User Events](#user-events)
6. [System Events](#system-events)
7. [Business Domain Events](#business-domain-events)
8. [Payload-Struktur](#payload-struktur)
9. [Signatur-Verifizierung](#signatur-verifizierung)
10. [Retry-Logik](#retry-logik)
11. [Best Practices](#best-practices)

---

## Webhook-Konfiguration

### Webhook erstellen (API)

```http
POST /api/v1/webhooks
Authorization: Bearer {token}
Content-Type: application/json

{
  "url": "https://ihre-app.de/webhooks/ablage",
  "events": ["document.created", "document.processed", "ocr.completed"],
  "secret": "whsec_...",
  "description": "ERP-Integration",
  "active": true,
  "headers": {
    "X-Custom-Header": "value"
  }
}
```

**Response:**
```json
{
  "id": "wh_abc123",
  "url": "https://ihre-app.de/webhooks/ablage",
  "events": ["document.created", "document.processed", "ocr.completed"],
  "active": true,
  "created_at": "2025-01-08T10:00:00Z",
  "signing_secret": "whsec_..."
}
```

### Webhook-Konfigurationsoptionen

| Option | Typ | Beschreibung |
|--------|-----|--------------|
| `url` | string | Endpoint-URL (HTTPS erforderlich) |
| `events` | array | Liste der zu abonnierenden Events |
| `secret` | string | Signing-Secret für Signatur-Verifizierung |
| `active` | boolean | Webhook aktiv/inaktiv |
| `headers` | object | Zusätzliche HTTP-Header |
| `retry_policy` | string | `exponential`, `linear`, `none` |
| `timeout_ms` | integer | Timeout in Millisekunden (max: 30000) |

---

## Event-Kategorien

### Übersicht aller Events

| Kategorie | Events | Beschreibung |
|-----------|--------|--------------|
| **Document** | 8 Events | Dokumenten-Lifecycle |
| **OCR** | 5 Events | OCR-Verarbeitung |
| **User** | 6 Events | Benutzerverwaltung |
| **System** | 4 Events | Systemereignisse |
| **Business** | 12 Events | Geschäftslogik |

### Event-Naming-Konvention

```
{resource}.{action}[.{detail}]

Beispiele:
- document.created
- ocr.completed
- invoice.extracted.verified
```

---

## Document Events

### `document.created`

Ausgelöst wenn ein Dokument hochgeladen wurde.

**Trigger:** Upload abgeschlossen, Validierung erfolgreich

```json
{
  "event": "document.created",
  "timestamp": "2025-01-08T10:30:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "rechnung_2025-01.pdf",
      "original_filename": "Rechnung_2025-01_Mustermann.pdf",
      "mime_type": "application/pdf",
      "file_size": 245678,
      "status": "pending",
      "owner_id": "usr_abc123",
      "folder_id": "fld_def456",
      "created_at": "2025-01-08T10:30:00.000Z"
    },
    "metadata": {
      "upload_source": "web",
      "client_ip": "192.168.1.100"
    }
  }
}
```

### `document.processing`

Ausgelöst wenn die OCR-Verarbeitung startet.

**Trigger:** OCR-Job gestartet

```json
{
  "event": "document.processing",
  "timestamp": "2025-01-08T10:30:05.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "status": "processing"
    },
    "job": {
      "id": "job_ghi789",
      "backend": "deepseek",
      "priority": 0,
      "started_at": "2025-01-08T10:30:05.000Z"
    }
  }
}
```

### `document.processed`

Ausgelöst wenn die Verarbeitung abgeschlossen ist.

**Trigger:** OCR-Verarbeitung erfolgreich, Klassifizierung abgeschlossen

```json
{
  "event": "document.processed",
  "timestamp": "2025-01-08T10:30:15.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "rechnung_2025-01.pdf",
      "status": "completed",
      "document_type": "invoice",
      "confidence_score": 0.95,
      "processing_time_ms": 2340,
      "page_count": 2
    },
    "extracted_data": {
      "has_text": true,
      "text_length": 1234,
      "has_tables": true,
      "table_count": 1,
      "language": "de"
    },
    "classification": {
      "type": "invoice",
      "confidence": 0.95,
      "alternatives": [
        {"type": "order", "confidence": 0.03},
        {"type": "letter", "confidence": 0.02}
      ]
    }
  }
}
```

### `document.failed`

Ausgelöst wenn die Verarbeitung fehlschlägt.

**Trigger:** OCR-Fehler, Timeout, ungültiges Format

```json
{
  "event": "document.failed",
  "timestamp": "2025-01-08T10:31:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "corrupted_file.pdf",
      "status": "failed"
    },
    "error": {
      "code": "OCR_PROCESSING_ERROR",
      "message": "Dokument konnte nicht verarbeitet werden",
      "details": "PDF-Struktur beschädigt",
      "retry_count": 3,
      "will_retry": false
    }
  }
}
```

### `document.updated`

Ausgelöst wenn Dokumentmetadaten geändert werden.

**Trigger:** Metadaten-Update, Tag-Änderung, Klassifizierungs-Korrektur

```json
{
  "event": "document.updated",
  "timestamp": "2025-01-08T11:00:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789"
    },
    "changes": {
      "document_type": {
        "old": "letter",
        "new": "invoice"
      },
      "tags": {
        "added": ["wichtig", "q1-2025"],
        "removed": []
      }
    },
    "updated_by": "usr_abc123"
  }
}
```

### `document.deleted`

Ausgelöst wenn ein Dokument gelöscht wird.

**Trigger:** Soft-Delete (Papierkorb) oder Hard-Delete

```json
{
  "event": "document.deleted",
  "timestamp": "2025-01-08T12:00:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "rechnung_2025-01.pdf"
    },
    "deletion_type": "soft",
    "deleted_by": "usr_abc123",
    "restore_until": "2025-02-07T12:00:00.000Z"
  }
}
```

### `document.restored`

Ausgelöst wenn ein Dokument wiederhergestellt wird.

**Trigger:** Wiederherstellung aus Papierkorb

```json
{
  "event": "document.restored",
  "timestamp": "2025-01-08T12:30:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "rechnung_2025-01.pdf",
      "status": "completed"
    },
    "restored_by": "usr_abc123"
  }
}
```

### `document.shared`

Ausgelöst wenn ein Dokument freigegeben wird.

**Trigger:** Freigabe erstellt oder geändert

```json
{
  "event": "document.shared",
  "timestamp": "2025-01-08T13:00:00.000Z",
  "data": {
    "document": {
      "id": "doc_xyz789"
    },
    "share": {
      "id": "shr_abc123",
      "shared_with": {
        "type": "user",
        "id": "usr_def456",
        "email": "kollege@firma.de"
      },
      "permission": "read",
      "expires_at": "2025-02-08T13:00:00.000Z"
    },
    "shared_by": "usr_abc123"
  }
}
```

---

## OCR Events

### `ocr.started`

Ausgelöst wenn OCR-Verarbeitung beginnt.

```json
{
  "event": "ocr.started",
  "timestamp": "2025-01-08T10:30:05.000Z",
  "data": {
    "job_id": "job_ghi789",
    "document_id": "doc_xyz789",
    "backend": "deepseek",
    "config": {
      "language": "de",
      "detect_tables": true,
      "detect_layout": true
    }
  }
}
```

### `ocr.completed`

Ausgelöst wenn OCR erfolgreich abgeschlossen ist.

```json
{
  "event": "ocr.completed",
  "timestamp": "2025-01-08T10:30:15.000Z",
  "data": {
    "job_id": "job_ghi789",
    "document_id": "doc_xyz789",
    "backend": "deepseek",
    "result": {
      "text_length": 1234,
      "confidence": 0.95,
      "page_count": 2,
      "processing_time_ms": 2340,
      "gpu_used": true,
      "memory_peak_mb": 8500
    },
    "quality_metrics": {
      "cer": 0.02,
      "wer": 0.05,
      "umlaut_accuracy": 0.99
    }
  }
}
```

### `ocr.failed`

Ausgelöst wenn OCR fehlschlägt.

```json
{
  "event": "ocr.failed",
  "timestamp": "2025-01-08T10:31:00.000Z",
  "data": {
    "job_id": "job_ghi789",
    "document_id": "doc_xyz789",
    "backend": "deepseek",
    "error": {
      "code": "GPU_OOM",
      "message": "GPU-Speicher erschöpft",
      "fallback_available": true,
      "will_retry": true,
      "next_backend": "surya"
    }
  }
}
```

### `ocr.corrected`

Ausgelöst wenn OCR-Text manuell korrigiert wird.

```json
{
  "event": "ocr.corrected",
  "timestamp": "2025-01-08T14:00:00.000Z",
  "data": {
    "document_id": "doc_xyz789",
    "correction": {
      "original": "Rechnung Nr. 12345",
      "corrected": "Rechnung Nr. 12346",
      "field": "invoice_number",
      "corrected_by": "usr_abc123"
    },
    "training_sample_created": true
  }
}
```

### `ocr.quality_alert`

Ausgelöst wenn OCR-Qualität unter Schwellenwert fällt.

```json
{
  "event": "ocr.quality_alert",
  "timestamp": "2025-01-08T15:00:00.000Z",
  "data": {
    "document_id": "doc_xyz789",
    "backend": "got_ocr",
    "quality_metrics": {
      "confidence": 0.65,
      "threshold": 0.80,
      "umlaut_errors": 5
    },
    "recommendation": "manual_review_required"
  }
}
```

---

## User Events

### `user.created`

```json
{
  "event": "user.created",
  "timestamp": "2025-01-08T09:00:00.000Z",
  "data": {
    "user": {
      "id": "usr_new123",
      "email": "neuer.mitarbeiter@firma.de",
      "full_name": "Max Mustermann",
      "role": "user"
    },
    "created_by": "usr_admin001",
    "invitation_sent": true
  }
}
```

### `user.activated`

```json
{
  "event": "user.activated",
  "timestamp": "2025-01-08T09:30:00.000Z",
  "data": {
    "user": {
      "id": "usr_new123",
      "email": "neuer.mitarbeiter@firma.de"
    },
    "activation_method": "email_link"
  }
}
```

### `user.login`

```json
{
  "event": "user.login",
  "timestamp": "2025-01-08T10:00:00.000Z",
  "data": {
    "user": {
      "id": "usr_abc123",
      "email": "user@firma.de"
    },
    "session": {
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "mfa_used": true
    }
  }
}
```

### `user.logout`

```json
{
  "event": "user.logout",
  "timestamp": "2025-01-08T18:00:00.000Z",
  "data": {
    "user": {
      "id": "usr_abc123"
    },
    "session_duration_minutes": 480
  }
}
```

### `user.permission_changed`

```json
{
  "event": "user.permission_changed",
  "timestamp": "2025-01-08T11:00:00.000Z",
  "data": {
    "user": {
      "id": "usr_abc123"
    },
    "changes": {
      "roles": {
        "added": ["editor"],
        "removed": ["viewer"]
      }
    },
    "changed_by": "usr_admin001"
  }
}
```

### `user.deactivated`

```json
{
  "event": "user.deactivated",
  "timestamp": "2025-01-08T17:00:00.000Z",
  "data": {
    "user": {
      "id": "usr_abc123",
      "email": "ex-mitarbeiter@firma.de"
    },
    "reason": "employee_offboarding",
    "deactivated_by": "usr_admin001",
    "documents_reassigned_to": "usr_manager001"
  }
}
```

---

## System Events

### `system.health_degraded`

```json
{
  "event": "system.health_degraded",
  "timestamp": "2025-01-08T14:00:00.000Z",
  "data": {
    "component": "gpu",
    "status": "degraded",
    "details": {
      "memory_usage_percent": 92,
      "temperature_celsius": 85,
      "processing_queue_length": 150
    },
    "impact": "ocr_processing_delayed",
    "estimated_recovery": "2025-01-08T14:30:00.000Z"
  }
}
```

### `system.health_recovered`

```json
{
  "event": "system.health_recovered",
  "timestamp": "2025-01-08T14:25:00.000Z",
  "data": {
    "component": "gpu",
    "status": "healthy",
    "downtime_minutes": 25
  }
}
```

### `system.backup_completed`

```json
{
  "event": "system.backup_completed",
  "timestamp": "2025-01-08T03:00:00.000Z",
  "data": {
    "backup": {
      "id": "bkp_20250108_030000",
      "type": "full",
      "size_gb": 45.6,
      "duration_minutes": 28,
      "components": ["database", "files", "config"]
    },
    "storage": {
      "location": "/backups/daily/",
      "retention_days": 30
    }
  }
}
```

### `system.maintenance_scheduled`

```json
{
  "event": "system.maintenance_scheduled",
  "timestamp": "2025-01-07T16:00:00.000Z",
  "data": {
    "maintenance": {
      "id": "mnt_20250108",
      "type": "database_upgrade",
      "scheduled_start": "2025-01-08T02:00:00.000Z",
      "estimated_duration_minutes": 60,
      "impact": "system_unavailable"
    },
    "notification_sent_to": ["all_users", "admins"]
  }
}
```

---

## Business Domain Events

### Invoice Events

#### `invoice.extracted`

```json
{
  "event": "invoice.extracted",
  "timestamp": "2025-01-08T10:30:20.000Z",
  "data": {
    "document_id": "doc_xyz789",
    "invoice": {
      "id": "inv_abc123",
      "invoice_number": "RE-2025-0001",
      "invoice_date": "2025-01-05",
      "due_date": "2025-02-04",
      "vendor": {
        "name": "Lieferant GmbH",
        "tax_id": "DE123456789"
      },
      "amounts": {
        "net": 1000.00,
        "tax": 190.00,
        "gross": 1190.00,
        "currency": "EUR"
      },
      "line_items_count": 5,
      "confidence": 0.92
    }
  }
}
```

#### `invoice.verified`

```json
{
  "event": "invoice.verified",
  "timestamp": "2025-01-08T11:00:00.000Z",
  "data": {
    "invoice_id": "inv_abc123",
    "verified_by": "usr_buchhalter001",
    "verification": {
      "amounts_correct": true,
      "vendor_matched": true,
      "duplicate_check": "passed"
    }
  }
}
```

#### `invoice.matched`

```json
{
  "event": "invoice.matched",
  "timestamp": "2025-01-08T11:30:00.000Z",
  "data": {
    "invoice_id": "inv_abc123",
    "match": {
      "type": "bank_transaction",
      "transaction_id": "txn_def456",
      "confidence": 0.95,
      "match_criteria": ["amount", "reference", "date"]
    }
  }
}
```

### Bank Statement Events

#### `bank_statement.imported`

```json
{
  "event": "bank_statement.imported",
  "timestamp": "2025-01-08T08:00:00.000Z",
  "data": {
    "document_id": "doc_bank001",
    "statement": {
      "id": "stmt_abc123",
      "account_iban": "DE89370400440532013000",
      "bank_name": "Commerzbank",
      "period": {
        "start": "2024-12-01",
        "end": "2024-12-31"
      },
      "transactions_count": 145,
      "opening_balance": 50000.00,
      "closing_balance": 62345.67
    }
  }
}
```

#### `transaction.categorized`

```json
{
  "event": "transaction.categorized",
  "timestamp": "2025-01-08T08:30:00.000Z",
  "data": {
    "transaction_id": "txn_def456",
    "categorization": {
      "category": "office_supplies",
      "confidence": 0.88,
      "auto_categorized": true
    }
  }
}
```

### Contract Events

#### `contract.extracted`

```json
{
  "event": "contract.extracted",
  "timestamp": "2025-01-08T10:00:00.000Z",
  "data": {
    "document_id": "doc_contract001",
    "contract": {
      "id": "ctr_abc123",
      "contract_number": "V-2025-0001",
      "type": "service_agreement",
      "parties": [
        {"role": "client", "name": "Unsere GmbH"},
        {"role": "provider", "name": "Dienstleister AG"}
      ],
      "dates": {
        "start": "2025-01-01",
        "end": "2025-12-31",
        "notice_period_days": 90
      },
      "confidence": 0.89
    }
  }
}
```

#### `contract.expiring`

```json
{
  "event": "contract.expiring",
  "timestamp": "2025-01-08T06:00:00.000Z",
  "data": {
    "contract_id": "ctr_abc123",
    "contract_number": "V-2024-0055",
    "expiration": {
      "date": "2025-02-28",
      "days_remaining": 51,
      "notice_deadline": "2025-01-30"
    },
    "notification_recipients": ["usr_legal001", "usr_manager001"]
  }
}
```

---

## Payload-Struktur

### Standard-Envelope

Alle Webhook-Payloads folgen dieser Struktur:

```json
{
  "id": "evt_unique_id",
  "event": "resource.action",
  "timestamp": "2025-01-08T10:30:00.000Z",
  "version": "v1",
  "data": {
    // Event-spezifische Daten
  },
  "metadata": {
    "tenant_id": "tnt_abc123",
    "correlation_id": "req_xyz789",
    "idempotency_key": "idem_123456"
  }
}
```

### Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `id` | string | Eindeutige Event-ID |
| `event` | string | Event-Typ |
| `timestamp` | string | ISO 8601 Zeitstempel (UTC) |
| `version` | string | API-Version |
| `data` | object | Event-spezifische Payload |
| `metadata.tenant_id` | string | Mandanten-ID |
| `metadata.correlation_id` | string | Request-Korrelations-ID |
| `metadata.idempotency_key` | string | Für Deduplizierung |

---

## Signatur-Verifizierung

### Signatur-Header

```http
X-Ablage-Signature: t=1704710400,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd
```

### Verifizierung (Python)

```python
import hmac
import hashlib
import time

def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300
) -> bool:
    """Verifiziert die Webhook-Signatur."""

    # Header parsen
    parts = dict(p.split('=') for p in signature_header.split(','))
    timestamp = int(parts['t'])
    signature = parts['v1']

    # Zeitfenster prüfen (Replay-Schutz)
    if abs(time.time() - timestamp) > tolerance_seconds:
        raise ValueError("Webhook timestamp outside tolerance window")

    # Signatur berechnen
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Signatur vergleichen (timing-safe)
    return hmac.compare_digest(expected, signature)
```

### Verifizierung (Node.js)

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signatureHeader, secret, toleranceSeconds = 300) {
  const parts = Object.fromEntries(
    signatureHeader.split(',').map(p => p.split('='))
  );

  const timestamp = parseInt(parts.t);
  const signature = parts.v1;

  // Zeitfenster prüfen
  if (Math.abs(Date.now() / 1000 - timestamp) > toleranceSeconds) {
    throw new Error('Webhook timestamp outside tolerance window');
  }

  // Signatur berechnen
  const signedPayload = `${timestamp}.${payload}`;
  const expected = crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');

  // Timing-safe Vergleich
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}
```

---

## Retry-Logik

### Retry-Verhalten

| Versuch | Wartezeit | Kumuliert |
|---------|-----------|-----------|
| 1 | Sofort | 0 |
| 2 | 1 Minute | 1 Min |
| 3 | 5 Minuten | 6 Min |
| 4 | 30 Minuten | 36 Min |
| 5 | 2 Stunden | 2.6 h |
| 6 | 8 Stunden | 10.6 h |
| 7 | 24 Stunden | 34.6 h |

### Erfolgreiche Antworten

Der Webhook gilt als erfolgreich bei:
- HTTP Status 2xx
- Antwort innerhalb von 30 Sekunden

### Fehlgeschlagene Antworten

Der Webhook wird wiederholt bei:
- HTTP Status 4xx (außer 400, 401, 403)
- HTTP Status 5xx
- Timeout (> 30 Sekunden)
- Verbindungsfehler

### Retry-Header

Bei Wiederholungen werden zusätzliche Header gesendet:

```http
X-Ablage-Retry-Count: 3
X-Ablage-Original-Timestamp: 2025-01-08T10:30:00.000Z
```

---

## Best Practices

### 1. Idempotenz implementieren

```python
@app.post("/webhooks/ablage")
async def handle_webhook(request: Request):
    payload = await request.json()
    event_id = payload["id"]

    # Prüfen ob Event bereits verarbeitet
    if await is_event_processed(event_id):
        return {"status": "already_processed"}

    # Event verarbeiten
    await process_event(payload)

    # Als verarbeitet markieren
    await mark_event_processed(event_id)

    return {"status": "processed"}
```

### 2. Asynchron verarbeiten

```python
@app.post("/webhooks/ablage")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()

    # Sofort 200 zurückgeben
    background_tasks.add_task(process_webhook_async, payload)

    return {"status": "accepted"}
```

### 3. Signatur immer verifizieren

```python
@app.post("/webhooks/ablage")
async def handle_webhook(request: Request):
    signature = request.headers.get("X-Ablage-Signature")
    body = await request.body()

    if not verify_webhook_signature(body, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Weiter verarbeiten...
```

### 4. Fehler graceful behandeln

```python
@app.post("/webhooks/ablage")
async def handle_webhook(request: Request):
    try:
        payload = await request.json()
        await process_event(payload)
        return {"status": "success"}
    except ValidationError as e:
        # Keine Wiederholung - Payload ungültig
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except ExternalServiceError as e:
        # Wiederholung gewünscht
        return JSONResponse(
            status_code=503,
            content={"error": "temporary_failure"}
        )
```

### 5. Logging einrichten

```python
import structlog

logger = structlog.get_logger()

@app.post("/webhooks/ablage")
async def handle_webhook(request: Request):
    payload = await request.json()

    logger.info(
        "webhook_received",
        event_type=payload["event"],
        event_id=payload["id"],
        timestamp=payload["timestamp"]
    )

    # Verarbeiten...

    logger.info(
        "webhook_processed",
        event_id=payload["id"],
        processing_time_ms=elapsed
    )
```

---

## Webhook-Testmodus

### Test-Events senden

```http
POST /api/v1/webhooks/{webhook_id}/test
Authorization: Bearer {token}
Content-Type: application/json

{
  "event": "document.created",
  "data": {
    "document": {
      "id": "doc_test123",
      "filename": "test.pdf"
    }
  }
}
```

### Webhook-Logs abrufen

```http
GET /api/v1/webhooks/{webhook_id}/logs?limit=50
Authorization: Bearer {token}
```

**Response:**
```json
{
  "logs": [
    {
      "id": "log_abc123",
      "event_id": "evt_xyz789",
      "event_type": "document.created",
      "status": "success",
      "http_status": 200,
      "response_time_ms": 245,
      "attempt": 1,
      "created_at": "2025-01-08T10:30:00.000Z"
    }
  ]
}
```

---

*Letzte Aktualisierung: Januar 2025*
