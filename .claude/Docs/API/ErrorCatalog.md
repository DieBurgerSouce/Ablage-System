# API Error Catalog

## Übersicht

Standardisierte Fehlerresponses für alle API-Endpoints der Ablage-System OCR Platform.

---

## Fehler-Format

### Standard Error Response

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Dokument nicht gefunden",
    "details": {
      "document_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    "timestamp": "2024-12-18T14:30:00Z",
    "request_id": "req_abc123"
  }
}
```

### Validierungsfehler

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validierungsfehler",
    "details": {
      "errors": [
        {
          "field": "email",
          "message": "Ungültige E-Mail-Adresse",
          "code": "INVALID_FORMAT"
        },
        {
          "field": "amount",
          "message": "Betrag muss positiv sein",
          "code": "MIN_VALUE"
        }
      ]
    }
  }
}
```

---

## HTTP Status Codes

| Code | Bedeutung | Verwendung |
|------|-----------|------------|
| `200` | OK | Erfolgreiche Anfrage |
| `201` | Created | Ressource erstellt |
| `204` | No Content | Erfolgreich, keine Daten |
| `400` | Bad Request | Ungültige Anfrage |
| `401` | Unauthorized | Nicht authentifiziert |
| `403` | Forbidden | Keine Berechtigung |
| `404` | Not Found | Ressource nicht gefunden |
| `409` | Conflict | Konflikt (z.B. Duplikat) |
| `422` | Unprocessable Entity | Validierungsfehler |
| `429` | Too Many Requests | Rate Limit erreicht |
| `500` | Internal Server Error | Serverfehler |
| `503` | Service Unavailable | Service nicht verfügbar |

---

## Fehlerkategorien

### 1. Authentifizierung (AUTH_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Ungültige Anmeldedaten |
| `AUTH_TOKEN_EXPIRED` | 401 | Token abgelaufen |
| `AUTH_TOKEN_INVALID` | 401 | Ungültiges Token |
| `AUTH_REFRESH_FAILED` | 401 | Token-Refresh fehlgeschlagen |
| `AUTH_MFA_REQUIRED` | 401 | 2FA erforderlich |
| `AUTH_MFA_INVALID` | 401 | Ungültiger 2FA-Code |
| `AUTH_ACCOUNT_LOCKED` | 403 | Konto gesperrt |
| `AUTH_ACCOUNT_DISABLED` | 403 | Konto deaktiviert |

**Beispiel**:
```json
{
  "error": {
    "code": "AUTH_TOKEN_EXPIRED",
    "message": "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
    "details": {
      "expired_at": "2024-12-18T14:00:00Z"
    }
  }
}
```

### 2. Berechtigung (PERM_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `PERM_DENIED` | 403 | Allgemein keine Berechtigung |
| `PERM_DOCUMENT_ACCESS` | 403 | Kein Zugriff auf Dokument |
| `PERM_ADMIN_REQUIRED` | 403 | Admin-Rechte erforderlich |
| `PERM_OWNER_REQUIRED` | 403 | Eigentümer-Rechte erforderlich |
| `PERM_FEATURE_DISABLED` | 403 | Feature nicht freigeschaltet |

### 3. Dokumente (DOC_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `DOC_NOT_FOUND` | 404 | Dokument nicht gefunden |
| `DOC_ALREADY_EXISTS` | 409 | Dokument existiert bereits |
| `DOC_INVALID_FORMAT` | 422 | Ungültiges Dateiformat |
| `DOC_TOO_LARGE` | 422 | Datei zu groß |
| `DOC_CORRUPT` | 422 | Datei beschädigt |
| `DOC_LOCKED` | 409 | Dokument ist gesperrt |
| `DOC_DELETED` | 410 | Dokument wurde gelöscht |
| `DOC_PROCESSING` | 409 | Dokument wird verarbeitet |

**Beispiel**:
```json
{
  "error": {
    "code": "DOC_TOO_LARGE",
    "message": "Die Datei überschreitet die maximale Größe von 50 MB.",
    "details": {
      "max_size_mb": 50,
      "actual_size_mb": 78.5
    }
  }
}
```

### 4. OCR-Verarbeitung (OCR_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `OCR_PROCESSING_FAILED` | 500 | OCR-Verarbeitung fehlgeschlagen |
| `OCR_BACKEND_UNAVAILABLE` | 503 | OCR-Backend nicht verfügbar |
| `OCR_GPU_OOM` | 503 | GPU-Speicher erschöpft |
| `OCR_TIMEOUT` | 504 | OCR-Timeout |
| `OCR_UNSUPPORTED_FORMAT` | 422 | Format nicht unterstützt |
| `OCR_LOW_QUALITY` | 422 | Bildqualität zu niedrig |
| `OCR_NO_TEXT` | 200 | Kein Text erkannt (Warnung) |

**Beispiel**:
```json
{
  "error": {
    "code": "OCR_GPU_OOM",
    "message": "GPU-Speicher erschöpft. Verarbeitung wird mit CPU-Fallback wiederholt.",
    "details": {
      "gpu_memory_gb": 16,
      "required_gb": 24,
      "fallback": "surya-docling"
    }
  }
}
```

### 5. Banking (BANK_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `BANK_ACCOUNT_NOT_FOUND` | 404 | Bankkonto nicht gefunden |
| `BANK_TX_NOT_FOUND` | 404 | Transaktion nicht gefunden |
| `BANK_INVALID_IBAN` | 422 | Ungültige IBAN |
| `BANK_INVALID_BIC` | 422 | Ungültige BIC |
| `BANK_TAN_INVALID` | 401 | Ungültige TAN |
| `BANK_TAN_EXPIRED` | 401 | TAN abgelaufen |
| `BANK_TAN_MAX_ATTEMPTS` | 403 | Max. TAN-Versuche überschritten |
| `BANK_PAYMENT_LIMIT` | 422 | Zahlungslimit überschritten |
| `BANK_INSUFFICIENT_FUNDS` | 422 | Nicht genug Guthaben |
| `BANK_DUPLICATE_TX` | 409 | Doppelte Transaktion |

### 6. Validierung (VAL_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `VAL_REQUIRED_FIELD` | 422 | Pflichtfeld fehlt |
| `VAL_INVALID_FORMAT` | 422 | Ungültiges Format |
| `VAL_MIN_LENGTH` | 422 | Mindestlänge unterschritten |
| `VAL_MAX_LENGTH` | 422 | Maximallänge überschritten |
| `VAL_MIN_VALUE` | 422 | Mindestwert unterschritten |
| `VAL_MAX_VALUE` | 422 | Maximalwert überschritten |
| `VAL_INVALID_ENUM` | 422 | Ungültiger Enum-Wert |
| `VAL_INVALID_DATE` | 422 | Ungültiges Datum |
| `VAL_INVALID_UUID` | 422 | Ungültige UUID |

### 7. Rate Limiting (RATE_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `RATE_LIMIT_EXCEEDED` | 429 | Allgemeines Rate Limit |
| `RATE_LOGIN_EXCEEDED` | 429 | Login-Versuche erschöpft |
| `RATE_API_EXCEEDED` | 429 | API-Calls erschöpft |
| `RATE_OCR_EXCEEDED` | 429 | OCR-Verarbeitungen erschöpft |

**Beispiel**:
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Zu viele Anfragen. Bitte warten Sie.",
    "details": {
      "limit": 100,
      "window_minutes": 1,
      "retry_after_seconds": 45
    }
  }
}
```

### 8. System (SYS_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `SYS_INTERNAL_ERROR` | 500 | Interner Serverfehler |
| `SYS_DATABASE_ERROR` | 503 | Datenbankfehler |
| `SYS_STORAGE_ERROR` | 503 | Speicherfehler (MinIO) |
| `SYS_CACHE_ERROR` | 503 | Cache-Fehler (Redis) |
| `SYS_QUEUE_ERROR` | 503 | Queue-Fehler (Celery) |
| `SYS_MAINTENANCE` | 503 | Wartungsmodus |
| `SYS_OVERLOADED` | 503 | System überlastet |

---

## Fehlerbehandlung im Frontend

### TypeScript Error Handler

```typescript
// lib/api/error-handler.ts

interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

const ERROR_MESSAGES: Record<string, string> = {
  // Auth
  AUTH_INVALID_CREDENTIALS: "Benutzername oder Passwort falsch",
  AUTH_TOKEN_EXPIRED: "Sitzung abgelaufen. Bitte neu anmelden.",

  // Documents
  DOC_NOT_FOUND: "Dokument nicht gefunden",
  DOC_TOO_LARGE: "Datei zu groß (max. 50 MB)",

  // Default
  DEFAULT: "Ein Fehler ist aufgetreten",
};

export function getErrorMessage(error: ApiError): string {
  return ERROR_MESSAGES[error.code] || error.message || ERROR_MESSAGES.DEFAULT;
}

export function handleApiError(error: unknown): never {
  if (axios.isAxiosError(error) && error.response?.data?.error) {
    const apiError = error.response.data.error as ApiError;
    throw new Error(getErrorMessage(apiError));
  }
  throw error;
}
```

### React Query Error Handler

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      onError: (error) => {
        const message = getErrorMessage(error);
        toast.error(message);
      },
    },
  },
});
```

---

## Backend Error Handling

### FastAPI Exception Handler

```python
# app/core/exceptions.py

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

class ApiException(HTTPException):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)

@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request.state.request_id,
            }
        },
    )

# Verwendung
raise ApiException(
    code="DOC_NOT_FOUND",
    message="Dokument nicht gefunden",
    status_code=404,
    details={"document_id": str(document_id)},
)
```

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
