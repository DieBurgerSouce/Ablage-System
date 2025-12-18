# Rate Limits - API-Beschränkungen

## Übersicht

Die Ablage-System OCR Platform verwendet Rate Limiting zum Schutz vor Überlastung und Missbrauch.

---

## Rate Limit Übersicht

| Endpoint-Kategorie | Limit | Zeitfenster | Burst |
|--------------------|-------|-------------|-------|
| **Login** | 5 Versuche | 15 Minuten | 5 |
| **API (Standard)** | 100 Requests | 1 Minute | 20 |
| **API (Premium)** | 500 Requests | 1 Minute | 50 |
| **OCR-Verarbeitung** | 10 Dokumente | 1 Stunde | 3 |
| **OCR (Premium)** | 100 Dokumente | 1 Stunde | 10 |
| **File Upload** | 50 MB | 1 Minute | 100 MB |
| **Export** | 10 Requests | 1 Minute | 3 |
| **Webhooks** | 1000 Events | 1 Stunde | 100 |

---

## Response Headers

Bei jeder API-Response werden Rate-Limit-Informationen in den Headers zurückgegeben:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1702909800
X-RateLimit-Window: 60
```

| Header | Beschreibung |
|--------|--------------|
| `X-RateLimit-Limit` | Maximale Anfragen im Zeitfenster |
| `X-RateLimit-Remaining` | Verbleibende Anfragen |
| `X-RateLimit-Reset` | Unix-Timestamp für Reset |
| `X-RateLimit-Window` | Zeitfenster in Sekunden |

---

## Rate Limit Exceeded (429)

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Zu viele Anfragen. Bitte warten Sie.",
    "details": {
      "limit": 100,
      "window_seconds": 60,
      "retry_after_seconds": 45
    }
  }
}
```

**Response Headers**:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1702909800
```

---

## Endpoint-spezifische Limits

### 1. Authentifizierung

```
POST /api/v1/auth/login
- 5 Versuche pro 15 Minuten pro IP
- Bei Überschreitung: 15 Minuten Sperre

POST /api/v1/auth/refresh
- 20 Versuche pro Minute pro User
```

### 2. Dokumente

```
GET /api/v1/documents
- 100 Requests/Minute (Standard)
- 500 Requests/Minute (Premium)

POST /api/v1/documents
- 50 Uploads/Minute
- Max. 50 MB pro Datei
- Max. 100 MB pro Minute (Gesamt)

DELETE /api/v1/documents/{id}
- 50 Deletes/Minute
```

### 3. OCR-Verarbeitung

```
POST /api/v1/ocr/process
- 10 Dokumente/Stunde (Standard)
- 100 Dokumente/Stunde (Premium)
- Burst: 3-10 gleichzeitige Verarbeitungen

POST /api/v1/ocr/batch
- 5 Batch-Jobs/Stunde (Standard)
- 20 Batch-Jobs/Stunde (Premium)
- Max. 50 Dokumente pro Batch
```

### 4. Banking

```
POST /api/v1/banking/payments
- 50 Zahlungen/Stunde

POST /api/v1/banking/import
- 10 Imports/Stunde

POST /api/v1/banking/reconciliation/auto
- 5 Reconciliation-Läufe/Stunde
```

### 5. Export

```
GET /api/v1/export/*
- 10 Exports/Minute
- Max. 1000 Dokumente pro Export
```

### 6. Admin-Endpoints

```
/api/v1/admin/*
- 50 Requests/Minute
- Nur für Admins
```

---

## Rate Limiting Strategie

### Sliding Window

```python
# Redis-basiertes Sliding Window
def check_rate_limit(user_id: str, endpoint: str) -> bool:
    key = f"rate_limit:{user_id}:{endpoint}"
    window = 60  # Sekunden

    pipe = redis.pipeline()
    now = time.time()

    # Alte Einträge entfernen
    pipe.zremrangebyscore(key, 0, now - window)

    # Anzahl prüfen
    pipe.zcard(key)

    # Neuen Request hinzufügen
    pipe.zadd(key, {str(now): now})

    # TTL setzen
    pipe.expire(key, window)

    results = pipe.execute()
    count = results[1]

    return count < RATE_LIMITS[endpoint]
```

### Token Bucket (Burst-Handling)

```python
class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now
```

---

## Client-seitige Behandlung

### Retry mit Backoff

```typescript
// lib/api/retry.ts

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxRetries = 3
): Promise<Response> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const response = await fetch(url, options);

    if (response.status === 429) {
      const retryAfter = parseInt(
        response.headers.get("Retry-After") || "60"
      );

      // Exponentieller Backoff
      const delay = retryAfter * 1000 + Math.random() * 1000;
      await sleep(delay);
      continue;
    }

    return response;
  }

  throw new Error("Max retries exceeded");
}
```

### React Query Integration

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error?.response?.status === 429) {
          return failureCount < 3;
        }
        return failureCount < 1;
      },
      retryDelay: (attemptIndex, error) => {
        const retryAfter = error?.response?.headers?.get("Retry-After");
        if (retryAfter) {
          return parseInt(retryAfter) * 1000;
        }
        return Math.min(1000 * 2 ** attemptIndex, 30000);
      },
    },
  },
});
```

---

## Erhöhung der Limits

### Premium-Tarif

Höhere Limits für zahlende Kunden:

| Feature | Standard | Premium |
|---------|----------|---------|
| API Calls/Minute | 100 | 500 |
| OCR/Stunde | 10 | 100 |
| Max. Dateigröße | 50 MB | 200 MB |
| Batch-Größe | 10 | 100 |

### Enterprise (Self-Hosted)

Bei On-Premises-Installation können Limits angepasst werden:

```yaml
# config/rate_limits.yml
rate_limits:
  api:
    default: 1000  # Erhöht von 100
    burst: 100
  ocr:
    default: 500   # Erhöht von 10
    burst: 50
  upload:
    max_file_mb: 500
    max_total_mb: 1000
```

---

## Monitoring

### Prometheus-Metriken

```
# Rate Limit Hits
ablage_rate_limit_hits_total{endpoint="/api/v1/documents", status="allowed"} 1234
ablage_rate_limit_hits_total{endpoint="/api/v1/documents", status="blocked"} 56

# Current Usage
ablage_rate_limit_current{user="user123", endpoint="/api/v1/ocr"} 8
ablage_rate_limit_remaining{user="user123", endpoint="/api/v1/ocr"} 2
```

### Grafana Dashboard

- Rate Limit Übersicht pro Endpoint
- Top User nach API-Nutzung
- Blocked Requests Trend
- Burst-Nutzung

---

## Best Practices

### 1. Batching nutzen

```typescript
// ❌ Schlecht: 100 einzelne Requests
for (const id of documentIds) {
  await api.getDocument(id);
}

// ✓ Gut: 1 Batch-Request
await api.getDocuments(documentIds);
```

### 2. Caching implementieren

```typescript
// Client-seitiges Caching mit TanStack Query
const { data } = useQuery({
  queryKey: ["documents", filters],
  queryFn: () => api.getDocuments(filters),
  staleTime: 5 * 60 * 1000,  // 5 Minuten
  cacheTime: 30 * 60 * 1000, // 30 Minuten
});
```

### 3. Webhooks statt Polling

```typescript
// ❌ Schlecht: Polling
setInterval(() => api.checkStatus(jobId), 1000);

// ✓ Gut: Webhook-Callback
api.processDocument(docId, {
  webhook: "https://my-app.com/webhook/ocr-complete"
});
```

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
