# API Reference - Ablage-System OCR

> Vollstaendige REST API Dokumentation

**Base URL:** `https://ablage-system.example.com/api/v1`

**OpenAPI Docs:** `https://ablage-system.example.com/docs`

---

## Authentifizierung

Alle API-Endpoints (ausser `/auth/*` und `/health`) erfordern Authentifizierung.

### Bearer Token

```bash
curl -H "Authorization: Bearer <access_token>" https://api.example.com/api/v1/documents/
```

### Token erhalten

```bash
# Login
curl -X POST /api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "geheim"}'

# Antwort:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Token erneuern

```bash
curl -X POST /api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

---

## Endpoints Uebersicht

| Kategorie | Prefix | Beschreibung |
|-----------|--------|--------------|
| [Authentication](#authentication) | `/auth` | Login, Logout, Token |
| [Documents](#documents) | `/documents` | Upload, CRUD, Suche |
| [OCR](#ocr) | `/ocr` | OCR-Verarbeitung |
| [Search](#search) | `/search` | Volltext- und semantische Suche |
| [Banking](#banking) | `/banking` | Banking-Transaktionen |
| [RAG](#rag) | `/rag` | Retrieval Augmented Generation |
| [Admin](#admin) | `/admin` | Administration |
| [Health](#health) | `/health` | System-Status |

---

## Authentication

### POST /auth/login

Benutzer anmelden.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "geheim"
}
```

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "user"
  }
}
```

**Fehler:**
- `401`: Ungueltige Anmeldedaten
- `423`: Konto gesperrt (zu viele Fehlversuche)

### POST /auth/register

Neuen Benutzer registrieren.

**Request:**
```json
{
  "email": "neu@example.com",
  "password": "sicheres_passwort_123",
  "name": "Max Mustermann"
}
```

### POST /auth/logout

Abmelden und Token invalidieren.

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

### GET /auth/csrf-token

CSRF-Token fuer geschuetzte Anfragen abrufen.

---

## Documents

### POST /documents/

Dokument hochladen.

**Request (multipart/form-data):**
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `file` | File | PDF, PNG, JPG, TIFF (max 50MB) |
| `document_type` | string | `invoice`, `contract`, `receipt`, `form`, `letter`, `report`, `other` |
| `language` | string | `de` oder `en` (default: `de`) |
| `tags` | string | Kommaseparierte Tags |
| `start_ocr` | boolean | OCR automatisch starten (default: true) |
| `ocr_backend` | string | `auto`, `deepseek`, `got_ocr`, `surya` |
| `priority` | int | 1-10 (default: 5) |

**Beispiel:**
```bash
curl -X POST /api/v1/documents/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@rechnung.pdf" \
  -F "document_type=invoice" \
  -F "start_ocr=true"
```

**Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "rechnung.pdf",
  "status": "pending",
  "created_at": "2024-12-01T10:00:00Z",
  "ocr_task_id": "task-abc123"
}
```

### GET /documents/

Dokumente auflisten mit Filterung und Pagination.

**Query Parameter:**
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Offset (default: 0) |
| `limit` | int | Max. Ergebnisse (default: 100, max: 1000) |
| `status` | string | Filter: `pending`, `processing`, `completed`, `failed` |
| `document_type` | string | Filter nach Dokumenttyp |
| `tags` | string | Filter nach Tags (kommasepariert) |
| `created_after` | datetime | Filter: Erstellt nach |
| `created_before` | datetime | Filter: Erstellt vor |
| `order_by` | string | Sortierung: `created_at`, `filename`, `status` |
| `order_desc` | boolean | Absteigend sortieren |

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "filename": "rechnung.pdf",
      "document_type": "invoice",
      "status": "completed",
      "created_at": "2024-12-01T10:00:00Z",
      "extracted_text_preview": "Rechnung Nr. 12345..."
    }
  ],
  "total": 150,
  "skip": 0,
  "limit": 100
}
```

### GET /documents/{document_id}

Einzelnes Dokument abrufen.

**Response (200):**
```json
{
  "id": "uuid",
  "filename": "rechnung.pdf",
  "document_type": "invoice",
  "status": "completed",
  "language": "de",
  "file_size": 102400,
  "page_count": 3,
  "extracted_text": "Vollstaendiger extrahierter Text...",
  "ocr_backend": "deepseek",
  "ocr_confidence": 0.95,
  "entities": {
    "iban": ["DE89370400440532013000"],
    "dates": ["01.12.2024"],
    "amounts": ["1.234,56 EUR"]
  },
  "tags": ["wichtig", "2024"],
  "created_at": "2024-12-01T10:00:00Z",
  "updated_at": "2024-12-01T10:05:00Z"
}
```

### PATCH /documents/{document_id}

Dokument aktualisieren.

**Request:**
```json
{
  "document_type": "contract",
  "tags": ["vertrag", "2024"]
}
```

### DELETE /documents/{document_id}

Dokument loeschen (Soft-Delete, 30 Tage Retention).

**Response (200):**
```json
{
  "message": "Dokument zur Loeschung markiert",
  "retention_until": "2025-01-01T10:00:00Z"
}
```

### POST /documents/batch/delete

Mehrere Dokumente loeschen.

**Request:**
```json
{
  "document_ids": ["uuid1", "uuid2", "uuid3"]
}
```

### POST /documents/batch/export

Dokumente exportieren.

**Request:**
```json
{
  "document_ids": ["uuid1", "uuid2"],
  "format": "zip",
  "include_ocr_text": true
}
```

---

## OCR

### POST /ocr/preview/upload

Schnelle OCR-Vorschau ohne vollstaendige Verarbeitung.

**Request (multipart/form-data):**
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `file` | File | Dokument |
| `max_pages` | int | Max. Seiten (1-5, default: 1) |
| `max_chars` | int | Max. Zeichen (100-10000, default: 1000) |

**Response (200):**
```json
{
  "erfolg": true,
  "text": "Extrahierter Vorschau-Text...",
  "zeichen_anzahl": 850,
  "abgeschnitten": true,
  "methode": "deepseek"
}
```

### GET /ocr/status

OCR-System Status abrufen.

**Response (200):**
```json
{
  "verfuegbar": true,
  "backends": {
    "deepseek": {"status": "online", "vram_gb": 10.5},
    "got_ocr": {"status": "online"},
    "surya": {"status": "online"},
    "surya_gpu": {"status": "online", "vram_gb": 3.2}
  },
  "gpu_verfuegbar": true,
  "pymupdf_verfuegbar": true,
  "tesseract_verfuegbar": true
}
```

### POST /ocr/{document_id}/process

OCR-Verarbeitung fuer bestehendes Dokument starten.

**Query Parameter:**
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `backend` | string | `auto`, `deepseek`, `got_ocr`, `surya` |
| `priority` | int | 1-10 |

**Response (202):**
```json
{
  "task_id": "task-abc123",
  "status": "queued",
  "estimated_time_seconds": 30
}
```

---

## Search

### POST /search/

Volltext- und semantische Suche.

**Request:**
```json
{
  "query": "Rechnung Dezember 2024",
  "search_type": "hybrid",
  "filters": {
    "document_type": "invoice",
    "date_from": "2024-12-01",
    "date_to": "2024-12-31"
  },
  "limit": 20
}
```

| search_type | Beschreibung |
|-------------|--------------|
| `fulltext` | Nur Volltext-Suche |
| `semantic` | Nur semantische Vektorsuche |
| `hybrid` | Kombination (empfohlen) |

**Response (200):**
```json
{
  "results": [
    {
      "document_id": "uuid",
      "filename": "rechnung_dez.pdf",
      "score": 0.95,
      "highlight": "...Rechnung vom <em>Dezember 2024</em>..."
    }
  ],
  "total": 5,
  "query_time_ms": 45
}
```

### GET /search/similar/{document_id}

Aehnliche Dokumente finden.

**Response (200):**
```json
{
  "similar_documents": [
    {
      "document_id": "uuid2",
      "filename": "rechnung_nov.pdf",
      "similarity": 0.87
    }
  ]
}
```

---

## Banking

### GET /banking/accounts

Bankkonten auflisten.

### POST /banking/transactions/import

Transaktionen importieren (CSV, MT940, CAMT.053).

### GET /banking/reconciliation

Offene Posten zur Abstimmung.

### POST /banking/payments

Zahlung erstellen/vorschlagen.

---

## RAG

### POST /rag/chat

Chat mit Dokumenten (RAG).

**Request:**
```json
{
  "message": "Was steht in der Rechnung vom Dezember?",
  "document_ids": ["uuid1", "uuid2"],
  "conversation_id": "conv-123"
}
```

**Response (200):**
```json
{
  "response": "In der Rechnung vom Dezember...",
  "sources": [
    {"document_id": "uuid1", "chunk": "Relevanter Textabschnitt..."}
  ],
  "conversation_id": "conv-123"
}
```

### GET /rag/customers

Kundeninformationen aus Dokumenten extrahieren.

### POST /rag/search

Semantische Suche mit RAG-Kontext.

---

## Admin

### GET /admin/users

Benutzer auflisten (Admin only).

### POST /admin/users

Benutzer erstellen.

### GET /admin/audit

Audit-Log abrufen.

### GET /admin/system/status

System-Status und Metriken.

---

## Health

### GET /health

Basis-Health-Check (ohne Auth).

**Response (200):**
```json
{
  "status": "healthy",
  "timestamp": "2024-12-01T10:00:00Z"
}
```

### GET /health/detailed

Detaillierter Health-Check.

**Response (200):**
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "minio": "healthy",
    "gpu": "healthy"
  },
  "metrics": {
    "cpu_percent": 45.2,
    "memory_percent": 62.1,
    "gpu_memory_percent": 78.5
  }
}
```

---

## Rate Limits

| Tier | OCR/Stunde | OCR/Tag | API/Minute |
|------|------------|---------|------------|
| Free | 10 | 50 | 100 |
| Premium | 100 | 1000 | 500 |
| Admin | 10.000 | - | - |

**Rate-Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1701432000
```

---

## Fehlerbehandlung

Alle Fehler folgen dem Format:

```json
{
  "detail": "Fehlerbeschreibung auf Deutsch",
  "error_code": "DOCUMENT_NOT_FOUND",
  "timestamp": "2024-12-01T10:00:00Z"
}
```

### HTTP Status Codes

| Code | Beschreibung |
|------|--------------|
| 200 | Erfolgreich |
| 201 | Erstellt |
| 202 | Akzeptiert (async) |
| 400 | Ungueltige Anfrage |
| 401 | Nicht authentifiziert |
| 403 | Keine Berechtigung |
| 404 | Nicht gefunden |
| 409 | Konflikt |
| 422 | Validierungsfehler |
| 429 | Rate Limit ueberschritten |
| 500 | Serverfehler |
| 503 | Service nicht verfuegbar |

---

## Webhooks

Ereignis-Benachrichtigungen konfigurieren:

```bash
POST /api/v1/webhooks/
{
  "url": "https://example.com/webhook",
  "events": ["document.processed", "ocr.completed", "ocr.failed"],
  "secret": "webhook_secret_123"
}
```

### Webhook-Payload

```json
{
  "event": "document.processed",
  "timestamp": "2024-12-01T10:05:00Z",
  "data": {
    "document_id": "uuid",
    "status": "completed"
  },
  "signature": "sha256=..."
}
```

---

## SDK & Client Libraries

### Python

```python
from ablage_client import AblageClient

client = AblageClient(
    base_url="https://api.example.com",
    api_key="your_api_key"
)

# Dokument hochladen
doc = client.documents.upload("rechnung.pdf", document_type="invoice")

# OCR-Ergebnis abrufen
result = client.documents.get(doc.id)
print(result.extracted_text)
```

### TypeScript

```typescript
import { AblageClient } from '@ablage/client';

const client = new AblageClient({
  baseUrl: 'https://api.example.com',
  apiKey: 'your_api_key'
});

// Dokument hochladen
const doc = await client.documents.upload(file, { documentType: 'invoice' });

// OCR-Ergebnis abrufen
const result = await client.documents.get(doc.id);
console.log(result.extractedText);
```

---

## Weitere Dokumentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Systemarchitektur
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment-Anleitung
- [QUICKSTART.md](./QUICKSTART.md) - Schnellstart
- [OpenAPI Spec](https://ablage-system.example.com/openapi.json) - Auto-generierte Spec

---

*Version: 1.0 | Letzte Aktualisierung: 2024-12*
