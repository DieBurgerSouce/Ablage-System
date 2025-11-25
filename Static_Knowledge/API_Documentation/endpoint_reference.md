# API Endpoint Reference
**Ablage-System - Vollständige Endpoint-Dokumentation**

Version: 1.0
Last Updated: 2025-01-23
API Version: v1
Status: PRODUCTION

---

## Executive Summary

Complete reference documentation for all Ablage-System API endpoints, including request/response schemas, examples, and error cases.

**Endpoint Categories:**
- 🔐 Authentication (4 endpoints)
- 📄 Documents (7 endpoints)
- 👤 Users (4 endpoints)
- 🤖 OCR (3 endpoints)
- ❤️ Health (1 endpoint)

---

## Table of Contents

1. [Authentication Endpoints](#authentication-endpoints)
2. [Document Endpoints](#document-endpoints)
3. [User Endpoints](#user-endpoints)
4. [OCR Endpoints](#ocr-endpoints)
5. [Health Check](#health-check)

---

## Authentication Endpoints

### POST /api/v1/auth/login
**Beschreibung:** Benutzer anmelden und Access Token erhalten

**Request:**
```http
POST /api/v1/auth/login HTTP/1.1
Host: api.ablage.local
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "SecurePassword123"
}
```

**Request Schema:**
```json
{
  "username": "string (email format)",
  "password": "string (min length: 8)"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "user_123",
    "email": "user@example.com",
    "name": "Max Mustermann",
    "role": "user",
    "created_at": "2025-01-01T10:00:00Z"
  }
}
```

**Errors:**
- `401 AUTHENTICATION_FAILED`: Ungültige Anmeldedaten
- `429 RATE_LIMIT_EXCEEDED`: Zu viele Anmeldeversuche

---

### POST /api/v1/auth/refresh
**Beschreibung:** Access Token mit Refresh Token erneuern

**Request:**
```http
POST /api/v1/auth/refresh HTTP/1.1
Host: api.ablage.local
Cookie: refresh_token=<refresh_token>
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Errors:**
- `401 INVALID_TOKEN`: Refresh Token ungültig oder abgelaufen

---

### POST /api/v1/auth/logout
**Beschreibung:** Benutzer abmelden und Token invalidieren

**Request:**
```http
POST /api/v1/auth/logout HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (204 No Content)**

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert

---

### GET /api/v1/auth/me
**Beschreibung:** Aktuellen Benutzer abrufen

**Request:**
```http
GET /api/v1/auth/me HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "Max Mustermann",
  "role": "user",
  "created_at": "2025-01-01T10:00:00Z",
  "last_login": "2025-01-23T14:30:00Z",
  "storage_used_bytes": 1073741824,
  "storage_limit_bytes": 10737418240
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert

---

## Document Endpoints

### GET /api/v1/documents
**Beschreibung:** Liste aller Dokumente abrufen

**Request:**
```http
GET /api/v1/documents?page=1&per_page=20&sort=created_at&order=desc&tag=rechnung HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type    | Default | Beschreibung                      |
|-----------|---------|---------|-----------------------------------|
| page      | integer | 1       | Seitennummer (1-indexed)          |
| per_page  | integer | 20      | Anzahl pro Seite (max: 100)       |
| sort      | string  | created_at | Sortierfeld                    |
| order     | string  | desc    | Sortierrichtung (asc/desc)        |
| tag       | string  | -       | Nach Tag filtern                  |
| status    | string  | -       | Nach Status filtern               |
| from_date | date    | -       | Von Datum (ISO 8601)              |
| to_date   | date    | -       | Bis Datum (ISO 8601)              |

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "doc_123",
      "filename": "rechnung_2025_001.pdf",
      "file_size_bytes": 524288,
      "mime_type": "application/pdf",
      "status": "completed",
      "tags": ["rechnung", "2025"],
      "created_at": "2025-01-23T14:30:00Z",
      "updated_at": "2025-01-23T14:35:00Z",
      "owner_id": "user_123",
      "ocr_completed": true,
      "extracted_text_preview": "Rechnung Nr. 2025-001..."
    }
  ],
  "pagination": {
    "total": 156,
    "page": 1,
    "per_page": 20,
    "total_pages": 8
  }
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `422 VALIDATION_ERROR`: Ungültige Query Parameter

---

### POST /api/v1/documents
**Beschreibung:** Neues Dokument hochladen

**Request:**
```http
POST /api/v1/documents HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="file"; filename="rechnung.pdf"
Content-Type: application/pdf

<binary content>
------Boundary
Content-Disposition: form-data; name="tags"

rechnung,2025
------Boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"customer": "Firma GmbH", "invoice_number": "2025-001"}
------Boundary--
```

**Form Fields:**
| Field    | Type   | Required | Beschreibung                    |
|----------|--------|----------|---------------------------------|
| file     | file   | ✅ Yes   | Dokument-Datei (max 50 MB)      |
| tags     | string | ❌ No    | Komma-getrennte Tags            |
| metadata | json   | ❌ No    | Zusätzliche Metadaten           |

**Response (201 Created):**
```json
{
  "id": "doc_789",
  "filename": "rechnung.pdf",
  "file_size_bytes": 524288,
  "mime_type": "application/pdf",
  "status": "pending",
  "tags": ["rechnung", "2025"],
  "metadata": {
    "customer": "Firma GmbH",
    "invoice_number": "2025-001"
  },
  "created_at": "2025-01-23T15:00:00Z",
  "owner_id": "user_123",
  "upload_url": "/api/v1/documents/doc_789"
}
```

**Errors:**
- `400 BAD_REQUEST`: Ungültiges Dateiformat
- `413 PAYLOAD_TOO_LARGE`: Datei zu groß (>50 MB)
- `422 VALIDATION_ERROR`: Validierungsfehler

---

### GET /api/v1/documents/{id}
**Beschreibung:** Einzelnes Dokument abrufen

**Request:**
```http
GET /api/v1/documents/doc_123 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "doc_123",
  "filename": "rechnung_2025_001.pdf",
  "file_size_bytes": 524288,
  "mime_type": "application/pdf",
  "status": "completed",
  "tags": ["rechnung", "2025"],
  "metadata": {
    "customer": "Firma GmbH",
    "invoice_number": "2025-001"
  },
  "created_at": "2025-01-23T14:30:00Z",
  "updated_at": "2025-01-23T14:35:00Z",
  "owner_id": "user_123",
  "ocr_completed": true,
  "extracted_text": "Rechnung Nr. 2025-001\n\nFirma GmbH\nMusterstraße 123\n12345 Berlin\n\nRechnungsdatum: 23.01.2025\nUSt-IdNr.: DE123456789\n\nLeistung: Beratung\nBetrag: 1.500,00 €\n\nZahlbar bis: 06.02.2025",
  "ocr_backend": "deepseek",
  "ocr_confidence": 0.98,
  "processing_time_ms": 1250
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf dieses Dokument
- `404 NOT_FOUND`: Dokument nicht gefunden

---

### PATCH /api/v1/documents/{id}
**Beschreibung:** Dokument aktualisieren (Tags, Metadaten)

**Request:**
```http
PATCH /api/v1/documents/doc_123 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "tags": ["rechnung", "2025", "bezahlt"],
  "metadata": {
    "customer": "Firma GmbH",
    "invoice_number": "2025-001",
    "paid_date": "2025-02-01"
  }
}
```

**Request Schema:**
```json
{
  "tags": ["string"] (optional),
  "metadata": {object} (optional)
}
```

**Response (200 OK):**
```json
{
  "id": "doc_123",
  "filename": "rechnung_2025_001.pdf",
  "tags": ["rechnung", "2025", "bezahlt"],
  "metadata": {
    "customer": "Firma GmbH",
    "invoice_number": "2025-001",
    "paid_date": "2025-02-01"
  },
  "updated_at": "2025-01-23T16:00:00Z"
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf dieses Dokument
- `404 NOT_FOUND`: Dokument nicht gefunden
- `422 VALIDATION_ERROR`: Ungültige Daten

---

### DELETE /api/v1/documents/{id}
**Beschreibung:** Dokument löschen

**Request:**
```http
DELETE /api/v1/documents/doc_123 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (204 No Content)**

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf dieses Dokument
- `404 NOT_FOUND`: Dokument nicht gefunden

---

### GET /api/v1/documents/{id}/download
**Beschreibung:** Dokument herunterladen

**Request:**
```http
GET /api/v1/documents/doc_123/download HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="rechnung_2025_001.pdf"
Content-Length: 524288

<binary content>
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf dieses Dokument
- `404 NOT_FOUND`: Dokument nicht gefunden

---

### POST /api/v1/documents/{id}/ocr
**Beschreibung:** OCR-Verarbeitung für Dokument starten/wiederholen

**Request:**
```http
POST /api/v1/documents/doc_123/ocr HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "backend": "deepseek",
  "force_reprocess": false
}
```

**Request Schema:**
```json
{
  "backend": "string (deepseek|got_ocr|surya) (optional)",
  "force_reprocess": "boolean (default: false)"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_456",
  "document_id": "doc_123",
  "status": "queued",
  "backend": "deepseek",
  "estimated_time_seconds": 5,
  "status_url": "/api/v1/ocr/status/job_456"
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf dieses Dokument
- `404 NOT_FOUND`: Dokument nicht gefunden
- `409 CONFLICT`: OCR bereits in Bearbeitung

---

### GET /api/v1/documents/search
**Beschreibung:** Volltext-Suche in Dokumenten

**Request:**
```http
GET /api/v1/documents/search?q=Rechnung&tag=2025&from_date=2025-01-01 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type   | Required | Beschreibung                      |
|-----------|--------|----------|-----------------------------------|
| q         | string | ✅ Yes   | Suchbegriff                       |
| tag       | string | ❌ No    | Nach Tag filtern                  |
| from_date | date   | ❌ No    | Von Datum (ISO 8601)              |
| to_date   | date   | ❌ No    | Bis Datum (ISO 8601)              |
| page      | int    | ❌ No    | Seitennummer (default: 1)         |
| per_page  | int    | ❌ No    | Anzahl pro Seite (default: 20)    |

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "doc_123",
      "filename": "rechnung_2025_001.pdf",
      "relevance_score": 0.95,
      "matched_text": "...Rechnung Nr. 2025-001...",
      "highlight": "<em>Rechnung</em> Nr. 2025-001",
      "tags": ["rechnung", "2025"],
      "created_at": "2025-01-23T14:30:00Z"
    }
  ],
  "pagination": {
    "total": 12,
    "page": 1,
    "per_page": 20,
    "total_pages": 1
  },
  "query": {
    "search_term": "Rechnung",
    "filters": {
      "tag": "2025"
    },
    "execution_time_ms": 45
  }
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `422 VALIDATION_ERROR`: Ungültiger Suchbegriff

---

## User Endpoints

### GET /api/v1/users
**Beschreibung:** Liste aller Benutzer (nur Admin)

**Request:**
```http
GET /api/v1/users?page=1&per_page=20 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "user_123",
      "email": "user@example.com",
      "name": "Max Mustermann",
      "role": "user",
      "created_at": "2025-01-01T10:00:00Z",
      "last_login": "2025-01-23T14:30:00Z",
      "active": true
    }
  ],
  "pagination": {
    "total": 25,
    "page": 1,
    "per_page": 20,
    "total_pages": 2
  }
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Nur für Administratoren

---

### POST /api/v1/users
**Beschreibung:** Neuen Benutzer erstellen (nur Admin)

**Request:**
```http
POST /api/v1/users HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email": "newuser@example.com",
  "name": "Neuer Benutzer",
  "password": "SecurePassword123",
  "role": "user"
}
```

**Response (201 Created):**
```json
{
  "id": "user_789",
  "email": "newuser@example.com",
  "name": "Neuer Benutzer",
  "role": "user",
  "created_at": "2025-01-23T16:00:00Z",
  "active": true
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Nur für Administratoren
- `409 CONFLICT`: E-Mail bereits registriert
- `422 VALIDATION_ERROR`: Ungültige Daten

---

### GET /api/v1/users/{id}
**Beschreibung:** Benutzer abrufen

**Request:**
```http
GET /api/v1/users/user_123 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "Max Mustermann",
  "role": "user",
  "created_at": "2025-01-01T10:00:00Z",
  "last_login": "2025-01-23T14:30:00Z",
  "active": true,
  "storage_used_bytes": 1073741824,
  "storage_limit_bytes": 10737418240,
  "document_count": 156
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf diesen Benutzer
- `404 NOT_FOUND`: Benutzer nicht gefunden

---

### PATCH /api/v1/users/{id}
**Beschreibung:** Benutzer aktualisieren

**Request:**
```http
PATCH /api/v1/users/user_123 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Max Mustermann (aktualisiert)",
  "active": true
}
```

**Response (200 OK):**
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "Max Mustermann (aktualisiert)",
  "role": "user",
  "updated_at": "2025-01-23T16:30:00Z",
  "active": true
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `403 FORBIDDEN`: Kein Zugriff auf diesen Benutzer
- `404 NOT_FOUND`: Benutzer nicht gefunden
- `422 VALIDATION_ERROR`: Ungültige Daten

---

## OCR Endpoints

### POST /api/v1/ocr/process
**Beschreibung:** Einzelnes Dokument direkt verarbeiten (ohne vorherigen Upload)

**Request:**
```http
POST /api/v1/ocr/process HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

------Boundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

<binary content>
------Boundary
Content-Disposition: form-data; name="backend"

deepseek
------Boundary--
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_999",
  "status": "processing",
  "backend": "deepseek",
  "estimated_time_seconds": 5,
  "status_url": "/api/v1/ocr/status/job_999"
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `413 PAYLOAD_TOO_LARGE`: Datei zu groß
- `503 SERVICE_UNAVAILABLE`: OCR-Service überlastet

---

### GET /api/v1/ocr/backends
**Beschreibung:** Verfügbare OCR-Backends abrufen

**Request:**
```http
GET /api/v1/ocr/backends HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "backends": [
    {
      "name": "deepseek",
      "display_name": "DeepSeek-Janus-Pro",
      "description": "Multimodales VLM mit bester Genauigkeit für deutsche Texte",
      "accuracy": "high",
      "speed": "medium",
      "languages": ["de", "en"],
      "supports_fraktur": true,
      "gpu_required": true,
      "available": true
    },
    {
      "name": "got_ocr",
      "display_name": "GOT-OCR 2.0",
      "description": "Schnelles Transformer-basiertes OCR",
      "accuracy": "medium",
      "speed": "fast",
      "languages": ["de", "en", "multi"],
      "supports_fraktur": false,
      "gpu_required": true,
      "available": true
    },
    {
      "name": "surya",
      "display_name": "Surya + Docling",
      "description": "Layout-bewusstes OCR mit CPU-Unterstützung",
      "accuracy": "medium",
      "speed": "slow",
      "languages": ["de", "en", "multi"],
      "supports_fraktur": false,
      "gpu_required": false,
      "available": true
    }
  ]
}
```

---

### GET /api/v1/ocr/status/{job_id}
**Beschreibung:** OCR-Job-Status abrufen

**Request:**
```http
GET /api/v1/ocr/status/job_456 HTTP/1.1
Host: api.ablage.local
Authorization: Bearer <access_token>
```

**Response (200 OK) - Processing:**
```json
{
  "job_id": "job_456",
  "status": "processing",
  "progress": 65,
  "backend": "deepseek",
  "started_at": "2025-01-23T16:00:00Z",
  "estimated_completion": "2025-01-23T16:00:05Z"
}
```

**Response (200 OK) - Completed:**
```json
{
  "job_id": "job_456",
  "status": "completed",
  "progress": 100,
  "backend": "deepseek",
  "started_at": "2025-01-23T16:00:00Z",
  "completed_at": "2025-01-23T16:00:04Z",
  "processing_time_ms": 4250,
  "result": {
    "document_id": "doc_123",
    "extracted_text": "Rechnung Nr. 2025-001...",
    "confidence": 0.98,
    "page_count": 1
  }
}
```

**Response (200 OK) - Failed:**
```json
{
  "job_id": "job_456",
  "status": "failed",
  "backend": "deepseek",
  "started_at": "2025-01-23T16:00:00Z",
  "failed_at": "2025-01-23T16:00:02Z",
  "error": {
    "code": "GPU_OUT_OF_MEMORY",
    "message": "GPU-Speicher erschöpft",
    "details": "Versuchen Sie es später erneut oder verwenden Sie einen anderen Backend"
  }
}
```

**Errors:**
- `401 UNAUTHORIZED`: Nicht authentifiziert
- `404 NOT_FOUND`: Job nicht gefunden

---

## Health Check

### GET /api/v1/health
**Beschreibung:** System-Gesundheitsprüfung

**Request:**
```http
GET /api/v1/health HTTP/1.1
Host: api.ablage.local
```

**Response (200 OK) - Healthy:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-23T16:00:00Z",
  "version": "1.3.0",
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 5
    },
    "redis": {
      "status": "healthy",
      "response_time_ms": 2
    },
    "minio": {
      "status": "healthy",
      "response_time_ms": 8
    },
    "gpu": {
      "status": "healthy",
      "available": true,
      "memory_used_percent": 45
    },
    "disk_space": {
      "status": "healthy",
      "free_percent": 62
    }
  }
}
```

**Response (503 Service Unavailable) - Unhealthy:**
```json
{
  "status": "unhealthy",
  "timestamp": "2025-01-23T16:00:00Z",
  "version": "1.3.0",
  "checks": {
    "database": {
      "status": "unhealthy",
      "error": "Connection timeout"
    },
    "redis": {
      "status": "healthy",
      "response_time_ms": 2
    },
    "minio": {
      "status": "healthy",
      "response_time_ms": 8
    },
    "gpu": {
      "status": "unhealthy",
      "available": false,
      "error": "GPU not detected"
    },
    "disk_space": {
      "status": "warning",
      "free_percent": 15
    }
  }
}
```

---

## Related Documents

- [API Overview](api_overview.md)
- [Authentication Guide](authentication_guide.md)
- [API Client Examples](api_client_examples.md)
- [Error Handling Guide](error_handling_guide.md)
- [OpenAPI Specification](openapi_specification_guide.md)

---

## Revision History

| Version | Date       | Author   | Changes                         |
|---------|------------|----------|---------------------------------|
| 1.0     | 2025-01-23 | API Team | Initial endpoint reference      |

---

**"Documentation is a love letter that you write to your future self." - Damian Conway**

📚 **Endpoint Documentation Complete!**
