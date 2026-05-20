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

### 9. Parsing (PARSE_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `PARSE_AMOUNT_FAILED` | 422 | Betrag konnte nicht geparst werden |
| `PARSE_DATE_FAILED` | 422 | Datum konnte nicht geparst werden |
| `PARSE_VAT_RATE_FAILED` | 422 | MwSt-Satz konnte nicht geparst werden |
| `PARSE_CURRENCY_FAILED` | 422 | Währung konnte nicht erkannt werden |

**Beispiel**:
```json
{
  "error": {
    "code": "PARSE_AMOUNT_FAILED",
    "message": "Betrag konnte nicht geparst werden: Ungültiges Format",
    "details": {
      "raw_value": "12,34,56",
      "reason": "Mehrfache Dezimaltrenner"
    }
  }
}
```

### 10. Cache/Metrics (CACHE_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `CACHE_OPERATION_FAILED` | 503 | Cache-Operation fehlgeschlagen |
| `CACHE_METRICS_FAILED` | 503 | Metrik-Aufzeichnung fehlgeschlagen |
| `CACHE_POOL_EXHAUSTED` | 503 | Redis Connection Pool erschöpft |

**Hinweis**: Diese Fehler sind oft nicht-kritisch und werden nur geloggt.

### 11. Sicherheit (SEC_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `SEC_REDOS_BLOCKED` | 400 | Gefährliches Regex-Pattern blockiert |
| `SEC_MODULE_NOT_ALLOWED` | 403 | Modul nicht in Whitelist |
| `SEC_FUNCTION_NOT_ALLOWED` | 403 | Funktion nicht in Whitelist |
| `SEC_REGISTRATION_LOCKED` | 403 | BPMN-Registrierung gesperrt |
| `SEC_INVALID_COMPANY` | 400 | Ungültige Firmen-ID (JSONB) |
| `SEC_INVALID_FIELD` | 400 | Ungültiges Feld (JSONB) |

**Beispiel**:
```json
{
  "error": {
    "code": "SEC_REDOS_BLOCKED",
    "message": "Gefährliches Regex-Pattern blockiert (ReDoS-Schutz)",
    "details": {
      "pattern_length": 250,
      "reason": "Regex zu lang (max. 200 Zeichen)"
    }
  }
}
```

### 12. Fraud Detection (FRAUD_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `FRAUD_DOCUMENT_NOT_FOUND` | 404 | Dokument für Analyse nicht gefunden |
| `FRAUD_ENTITY_NOT_FOUND` | 404 | Geschäftspartner nicht gefunden |
| `FRAUD_ANALYSIS_FAILED` | 500 | Fraud-Analyse fehlgeschlagen |
| `FRAUD_CONFIG_INVALID` | 422 | Ungültige Fraud-Konfiguration |
| `FRAUD_ALERT_NOT_FOUND` | 404 | Fraud-Alert nicht gefunden |

**Beispiel**:
```json
{
  "error": {
    "code": "FRAUD_ANALYSIS_FAILED",
    "message": "Fraud-Analyse konnte nicht durchgeführt werden",
    "details": {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "reason": "Timeout bei ML-Modell"
    }
  }
}
```

### 13. Alert Center (ALERT_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `ALERT_NOT_FOUND` | 404 | Alert nicht gefunden |
| `ALERT_ALREADY_RESOLVED` | 409 | Alert bereits gelöst |
| `ALERT_INVALID_TRANSITION` | 422 | Ungültiger Statusübergang |
| `ALERT_BULK_PARTIAL_FAILURE` | 207 | Massenaktion teilweise fehlgeschlagen |
| `ALERT_ASSIGN_FAILED` | 400 | Zuweisung fehlgeschlagen |

### 14. Document Chains (CHAIN_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `CHAIN_NOT_FOUND` | 404 | Dokumentenkette nicht gefunden |
| `CHAIN_DOCUMENT_NOT_FOUND` | 404 | Dokument nicht gefunden |
| `CHAIN_DOCUMENT_ALREADY_LINKED` | 409 | Dokument bereits verknüpft |
| `CHAIN_INVALID_RELATIONSHIP` | 422 | Ungültige Beziehung |
| `CHAIN_SEQUENCE_ERROR` | 422 | Ungültige Dokumentenreihenfolge |
| `CHAIN_DISCREPANCY_NOT_FOUND` | 404 | Abweichung nicht gefunden |

### 15. Import (IMPORT_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `IMPORT_CONFIG_NOT_FOUND` | 404 | Import-Konfiguration nicht gefunden |
| `IMPORT_CONNECTION_FAILED` | 503 | Verbindung fehlgeschlagen (IMAP/Folder) |
| `IMPORT_RULE_NOT_FOUND` | 404 | Import-Regel nicht gefunden |
| `IMPORT_RULE_INVALID` | 422 | Ungültige Regel-Definition |
| `IMPORT_FILE_TOO_LARGE` | 413 | Datei zu groß |
| `IMPORT_UNSUPPORTED_FORMAT` | 415 | Nicht unterstütztes Format |

### 16. MLOps (MLOPS_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `MLOPS_MODEL_NOT_FOUND` | 404 | Modell-Version nicht gefunden |
| `MLOPS_TRAINING_FAILED` | 500 | Training fehlgeschlagen |
| `MLOPS_EVALUATION_FAILED` | 500 | Evaluation fehlgeschlagen |
| `MLOPS_ROLLBACK_FAILED` | 500 | Rollback fehlgeschlagen |
| `MLOPS_NO_ACTIVE_MODEL` | 404 | Kein aktives Modell vorhanden |

### 17. DLP (DLP_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `DLP_POLICY_NOT_FOUND` | 404 | DLP-Policy nicht gefunden |
| `DLP_POLICY_EXISTS` | 409 | Policy-Name existiert bereits |
| `DLP_ACCESS_DENIED` | 403 | Zugriff durch DLP-Policy verweigert |
| `DLP_SCAN_FAILED` | 500 | Sensible-Daten-Scan fehlgeschlagen |
| `DLP_INVALID_CONDITIONS` | 422 | Ungültige Policy-Bedingungen |

### 18. Shipment Tracking (SHIP_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `SHIP_NOT_FOUND` | 404 | Sendung nicht gefunden |
| `SHIP_TRACKING_FAILED` | 503 | Carrier-API nicht erreichbar |
| `SHIP_INVALID_NUMBER` | 422 | Ungültige Sendungsnummer |
| `SHIP_CARRIER_UNKNOWN` | 400 | Carrier nicht erkannt |

### 19. OCR Learning (LEARNING_*)

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `LEARNING_INVALID_BACKEND` | 400 | Backend nicht in Whitelist |
| `LEARNING_INVALID_FIELD` | 400 | Feldname ungültig |
| `LEARNING_INVALID_CONFIDENCE` | 422 | Confidence außerhalb 0.0-1.0 |
| `LEARNING_TEST_NOT_FOUND` | 404 | A/B-Test nicht gefunden |
| `LEARNING_TEST_ALREADY_EXISTS` | 409 | Test-ID existiert bereits |
| `LEARNING_TEST_ALREADY_ENDED` | 409 | Test bereits beendet |
| `LEARNING_INVALID_MODE` | 400 | Ungültiger Lernmodus |

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
| 2026-01-27 | 1.2 | Neue Kategorien: FRAUD, ALERT, CHAIN, IMPORT, MLOPS, DLP, SHIP, LEARNING |
| 2026-01-27 | 1.1 | Neue Kategorien: PARSE, CACHE, SEC |
| 2024-12-18 | 1.0 | Initial Release |
