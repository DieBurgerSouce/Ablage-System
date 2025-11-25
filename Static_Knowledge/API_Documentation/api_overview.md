# API Overview
**Ablage-System - RESTful API Dokumentation**

Version: 1.0
Last Updated: 2025-01-23
API Version: v1
Status: PRODUCTION

---

## Executive Summary

Complete API overview for Ablage-System, covering architecture, design principles, versioning, and core concepts.

**API Features:**
- ✅ RESTful design with resource-based URLs
- ✅ JWT authentication with refresh tokens
- ✅ Rate limiting: 100 requests/minute per user
- ✅ Pagination: Cursor-based for large datasets
- ✅ Versioning: URL path versioning (v1, v2)
- ✅ Error handling: Consistent error responses
- ✅ German language: All messages in German

---

## Table of Contents

1. [API Architecture](#api-architecture)
2. [Base URL](#base-url)
3. [Authentication](#authentication)
4. [Request Format](#request-format)
5. [Response Format](#response-format)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Pagination](#pagination)
9. [Versioning](#versioning)

---

## API Architecture

### System Architecture

```
Client (Browser/App)
       ↓
    HTTPS/TLS
       ↓
  Load Balancer
       ↓
  API Gateway (FastAPI)
       ↓
  ┌─────────────────────┐
  │  Business Logic     │
  ├─────────────────────┤
  │ - Authentication    │
  │ - Authorization     │
  │ - Validation        │
  │ - Rate Limiting     │
  └─────────────────────┘
       ↓
  ┌─────────────┬──────────────┬──────────────┐
  │  PostgreSQL │  Redis Cache │  MinIO S3    │
  │  (Metadata) │  (Sessions)  │  (Documents) │
  └─────────────┴──────────────┴──────────────┘
       ↓
  Celery Workers (OCR Processing)
```

### Technology Stack

- **Framework:** FastAPI 0.110+
- **Python:** 3.11+
- **Authentication:** JWT (JSON Web Tokens)
- **Validation:** Pydantic v2
- **Documentation:** OpenAPI 3.1, ReDoc, Swagger UI
- **Security:** OAuth2 with Password Flow
- **Rate Limiting:** Redis-backed

---

## Base URL

### Environments

**Production:**
```
https://api.ablage.local/api/v1
```

**Staging:**
```
https://api.staging.ablage.local/api/v1
```

**Development:**
```
http://localhost:8000/api/v1
```

### API Endpoints Structure

```
/api/v1/
├── /auth/                 # Authentication endpoints
│   ├── /login
│   ├── /logout
│   ├── /refresh
│   └── /me
│
├── /documents/            # Document management
│   ├── /                  # List, create
│   ├── /{id}              # Get, update, delete
│   ├── /{id}/download
│   ├── /{id}/ocr
│   └── /search
│
├── /users/                # User management
│   ├── /
│   ├── /{id}
│   └── /me
│
├── /ocr/                  # OCR operations
│   ├── /process
│   ├── /backends
│   └── /status/{job_id}
│
└── /health                # Health check
```

---

## Authentication

### JWT Token Authentication

**Flow:**
1. Client sends credentials to `/auth/login`
2. Server validates and returns access token + refresh token
3. Client includes access token in `Authorization` header for subsequent requests
4. When access token expires (15 min), use refresh token to get new access token

### Token Types

**Access Token:**
- Lifetime: 15 minutes
- Purpose: API access
- Storage: Memory (not localStorage)

**Refresh Token:**
- Lifetime: 7 days
- Purpose: Obtain new access token
- Storage: HttpOnly cookie

### Example: Login

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

**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: refresh_token=<token>; HttpOnly; Secure; SameSite=Strict

{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "user_123",
    "email": "user@example.com",
    "name": "Max Mustermann"
  }
}
```

### Example: Authenticated Request

```http
GET /api/v1/documents HTTP/1.1
Host: api.ablage.local
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Request Format

### HTTP Methods

| Method | Purpose              | Idempotent | Safe |
|--------|---------------------|------------|------|
| GET    | Retrieve resource   | ✅ Yes     | ✅ Yes |
| POST   | Create resource     | ❌ No      | ❌ No |
| PUT    | Update (replace)    | ✅ Yes     | ❌ No |
| PATCH  | Update (partial)    | ✅ Yes     | ❌ No |
| DELETE | Delete resource     | ✅ Yes     | ❌ No |

### Headers

**Required Headers:**
```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

**Optional Headers:**
```http
Accept-Language: de-DE
X-Request-ID: <uuid>
```

### Request Body

**JSON Format:**
```json
{
  "filename": "rechnung_2025_001.pdf",
  "tags": ["rechnung", "2025"],
  "metadata": {
    "customer": "Firma GmbH",
    "date": "2025-01-23"
  }
}
```

### File Upload

**Multipart Form Data:**
```http
POST /api/v1/documents/ HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

<binary content>
------Boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"tags": ["rechnung"]}
------Boundary--
```

---

## Response Format

### Success Response Structure

```json
{
  "data": {
    "id": "doc_123",
    "filename": "rechnung_2025_001.pdf",
    "status": "completed",
    "created_at": "2025-01-23T14:30:00Z"
  },
  "meta": {
    "request_id": "req_456",
    "timestamp": "2025-01-23T14:30:05Z"
  }
}
```

### List Response Structure

```json
{
  "data": [
    {"id": "doc_123", "filename": "document1.pdf"},
    {"id": "doc_124", "filename": "document2.pdf"}
  ],
  "pagination": {
    "total": 156,
    "page": 1,
    "per_page": 20,
    "total_pages": 8,
    "next_cursor": "eyJpZCI6MTAwfQ=="
  },
  "meta": {
    "request_id": "req_789",
    "timestamp": "2025-01-23T14:30:05Z"
  }
}
```

### HTTP Status Codes

| Code | Meaning                  | Usage                                    |
|------|--------------------------|------------------------------------------|
| 200  | OK                       | Successful GET, PUT, PATCH, DELETE       |
| 201  | Created                  | Successful POST (resource created)       |
| 202  | Accepted                 | Async operation accepted (OCR job)       |
| 204  | No Content               | Successful DELETE (no response body)     |
| 400  | Bad Request              | Invalid request format                   |
| 401  | Unauthorized             | Missing or invalid authentication        |
| 403  | Forbidden                | Authenticated but not authorized         |
| 404  | Not Found                | Resource does not exist                  |
| 409  | Conflict                 | Resource already exists                  |
| 422  | Unprocessable Entity     | Validation error                         |
| 429  | Too Many Requests        | Rate limit exceeded                      |
| 500  | Internal Server Error    | Unexpected server error                  |
| 503  | Service Unavailable      | Server overloaded or maintenance         |

---

## Error Handling

### Error Response Structure

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Ungültige Eingabedaten",
    "details": [
      {
        "field": "filename",
        "issue": "Dateiname ist erforderlich"
      },
      {
        "field": "file_size",
        "issue": "Datei zu groß (max. 50 MB)"
      }
    ]
  },
  "meta": {
    "request_id": "req_999",
    "timestamp": "2025-01-23T14:30:05Z"
  }
}
```

### Error Codes

| Code                    | HTTP Status | Bedeutung                              |
|-------------------------|-------------|----------------------------------------|
| AUTHENTICATION_FAILED   | 401         | Authentifizierung fehlgeschlagen       |
| INVALID_TOKEN           | 401         | Token ungültig oder abgelaufen         |
| ACCESS_DENIED           | 403         | Zugriff verweigert                     |
| RESOURCE_NOT_FOUND      | 404         | Ressource nicht gefunden               |
| VALIDATION_ERROR        | 422         | Validierungsfehler                     |
| RATE_LIMIT_EXCEEDED     | 429         | Rate-Limit überschritten               |
| OCR_PROCESSING_FAILED   | 500         | OCR-Verarbeitung fehlgeschlagen        |
| GPU_OUT_OF_MEMORY       | 503         | GPU-Speicher erschöpft                 |

### Example Error Responses

**400 Bad Request:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Ungültige Anfrage",
    "details": [
      {
        "field": "email",
        "issue": "E-Mail-Format ungültig"
      }
    ]
  }
}
```

**401 Unauthorized:**
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "Token ungültig oder abgelaufen",
    "details": []
  }
}
```

**404 Not Found:**
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Dokument nicht gefunden",
    "details": [
      {
        "resource": "document",
        "id": "doc_999"
      }
    ]
  }
}
```

**429 Rate Limit Exceeded:**
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate-Limit überschritten. Bitte versuchen Sie es später erneut.",
    "details": [
      {
        "limit": 100,
        "remaining": 0,
        "reset_at": "2025-01-23T15:00:00Z"
      }
    ]
  }
}
```

---

## Rate Limiting

### Limits by User Type

| User Type   | Requests/Minute | Requests/Hour | Requests/Day |
|-------------|-----------------|---------------|--------------|
| Anonymous   | 20              | 100           | 500          |
| Registered  | 100             | 1000          | 10000        |
| Premium     | 500             | 5000          | 50000        |
| Admin       | Unlimited       | Unlimited     | Unlimited    |

### Rate Limit Headers

**Response Headers:**
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1674567000
Retry-After: 42
```

### Rate Limit Response

**429 Too Many Requests:**
```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1674567000
Retry-After: 42

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Sie haben das Rate-Limit überschritten",
    "details": [
      {
        "limit": 100,
        "remaining": 0,
        "reset_at": "2025-01-23T15:00:00Z"
      }
    ]
  }
}
```

---

## Pagination

### Cursor-Based Pagination

**Query Parameters:**
- `limit`: Number of items per page (default: 20, max: 100)
- `cursor`: Opaque cursor for next page

**Example Request:**
```http
GET /api/v1/documents?limit=20&cursor=eyJpZCI6MTAwfQ== HTTP/1.1
```

**Example Response:**
```json
{
  "data": [
    {"id": "doc_101", "filename": "document101.pdf"},
    {"id": "doc_102", "filename": "document102.pdf"}
  ],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6MTIwfQ==",
    "previous_cursor": "eyJpZCI6ODB9"
  }
}
```

### Offset-Based Pagination (Alternative)

**Query Parameters:**
- `page`: Page number (1-indexed)
- `per_page`: Items per page (default: 20, max: 100)

**Example Request:**
```http
GET /api/v1/documents?page=2&per_page=20 HTTP/1.1
```

**Example Response:**
```json
{
  "data": [...],
  "pagination": {
    "total": 156,
    "page": 2,
    "per_page": 20,
    "total_pages": 8
  }
}
```

---

## Versioning

### URL Path Versioning

**Current Version:** v1

**Example:**
```
https://api.ablage.local/api/v1/documents
https://api.ablage.local/api/v2/documents  # Future version
```

### Version Lifecycle

| Version | Status      | Release Date | EOL Date   |
|---------|-------------|--------------|------------|
| v1      | Current     | 2025-01-01   | 2026-12-31 |
| v2      | Planned     | 2025-07-01   | TBD        |

### Deprecation Policy

1. **Announce deprecation:** 6 months before EOL
2. **Deprecation header:** `Deprecation: true`
3. **Sunset header:** `Sunset: Tue, 31 Dec 2026 23:59:59 GMT`
4. **Migration guide:** Published with deprecation announcement

**Deprecated Response:**
```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Tue, 31 Dec 2026 23:59:59 GMT
Link: <https://docs.ablage.local/migration/v1-to-v2>; rel="deprecation"

{
  "data": {...}
}
```

---

## Interactive Documentation

### Swagger UI

**URL:** https://api.ablage.local/docs

Interactive API documentation with "Try it out" functionality.

### ReDoc

**URL:** https://api.ablage.local/redoc

Alternative documentation with better readability and search.

### OpenAPI Specification

**URL:** https://api.ablage.local/openapi.json

Machine-readable API specification in OpenAPI 3.1 format.

---

## Client Libraries

### Official SDKs

**Python:**
```bash
pip install ablage-client
```

**JavaScript/TypeScript:**
```bash
npm install @ablage/client
```

**Usage Example (Python):**
```python
from ablage_client import AblageClient

client = AblageClient(
    api_key="your_api_key",
    base_url="https://api.ablage.local"
)

# Upload document
document = client.documents.create(
    file_path="rechnung.pdf",
    tags=["rechnung", "2025"]
)

# Get document
doc = client.documents.get(document.id)
print(f"Status: {doc.status}")
```

---

## Performance Targets

### Response Time Targets (P95)

| Endpoint Category       | Target  | Current |
|-------------------------|---------|---------|
| GET (single resource)   | <100ms  | 85ms    |
| GET (list)              | <300ms  | 245ms   |
| POST (create)           | <500ms  | 420ms   |
| POST (file upload)      | <2000ms | 1850ms  |
| DELETE                  | <200ms  | 150ms   |

### Availability Target

- **SLA:** 99.9% uptime
- **Downtime allowance:** 43 minutes/month
- **Maintenance window:** Sunday 02:00-04:00 CET

---

## Security

### HTTPS/TLS

- **Required:** All API requests must use HTTPS
- **TLS Version:** 1.3 minimum
- **Certificate:** Valid SSL certificate

### CORS

**Allowed Origins:**
```
https://app.ablage.local
https://staging.ablage.local
http://localhost:3000 (development only)
```

**Allowed Methods:**
```
GET, POST, PUT, PATCH, DELETE, OPTIONS
```

**Allowed Headers:**
```
Authorization, Content-Type, Accept, X-Request-ID
```

### Content Security

- **XSS Protection:** Enabled
- **CSRF Protection:** Required for state-changing operations
- **SQL Injection:** Parameterized queries only
- **Rate Limiting:** Enabled (see Rate Limiting section)

---

## Related Documents

- [Authentication Guide](authentication_guide.md)
- [Endpoint Reference](endpoint_reference.md)
- [API Client Examples](api_client_examples.md)
- [OpenAPI Specification Guide](openapi_specification_guide.md)
- [Error Handling Guide](error_handling_guide.md)

---

## Revision History

| Version | Date       | Author   | Changes                |
|---------|------------|----------|------------------------|
| 1.0     | 2025-01-23 | API Team | Initial API overview   |

---

**"Good API design is not just about functionality, it's about developer experience."**

🚀 **API Documentation Excellence!**
