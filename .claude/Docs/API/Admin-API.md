# Admin API Documentation

## Uebersicht

Die Admin-API bietet administrative Funktionen fuer das Ablage-System.
Alle Endpoints erfordern Admin-Berechtigung.

**Base URL:** `/api/v1/admin`

## Authentifizierung

Alle Admin-Endpoints erfordern:
- Gueltige JWT-Session
- Admin-Rolle (`is_admin: true` oder `role: admin`)

```bash
curl -H "Authorization: Bearer <admin-token>" \
     http://localhost:8000/api/v1/admin/...
```

## User Management

### Alle Benutzer auflisten

```http
GET /api/v1/admin/users
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| page | int | 1 | Seitennummer |
| limit | int | 50 | Eintraege pro Seite |
| is_active | bool | - | Nach Aktivstatus filtern |
| tier | string | - | Nach Tier filtern (free/premium/admin) |
| search | string | - | Suche in E-Mail/Name |

**Response:**
```json
{
  "total": 150,
  "page": 1,
  "limit": 50,
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "Max Mustermann",
      "is_active": true,
      "tier": "premium",
      "created_at": "2024-01-15T10:30:00Z",
      "last_activity_at": "2024-12-02T08:15:00Z",
      "document_count": 42
    }
  ]
}
```

### Benutzer Details

```http
GET /api/v1/admin/users/{user_id}
```

**Response:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "Max Mustermann",
  "is_active": true,
  "tier": "premium",
  "is_admin": false,
  "is_verified": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-11-20T14:00:00Z",
  "last_activity_at": "2024-12-02T08:15:00Z",
  "document_count": 42,
  "storage_used_bytes": 1073741824,
  "rate_limit_override": null,
  "mfa_enabled": true
}
```

### Benutzer aktualisieren

```http
PATCH /api/v1/admin/users/{user_id}
```

**Request Body:**
```json
{
  "is_active": true,
  "tier": "premium",
  "is_admin": false,
  "rate_limit_override": {
    "requests_per_minute": 200
  }
}
```

### Benutzer deaktivieren

```http
POST /api/v1/admin/users/{user_id}/deactivate
```

**Request Body:**
```json
{
  "reason": "Verstoß gegen Nutzungsbedingungen",
  "notify_user": true
}
```

### Benutzer loeschen (GDPR)

```http
DELETE /api/v1/admin/users/{user_id}
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| hard_delete | bool | false | Permanente Loeschung |
| delete_documents | bool | true | Dokumente mitloeschen |

## Rate Limiting

### Rate Limit Overrides auflisten

```http
GET /api/v1/admin/rate-limits
```

**Response:**
```json
{
  "overrides": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "user_email": "user@example.com",
      "limit_type": "api",
      "requests_per_minute": 500,
      "requests_per_hour": null,
      "valid_until": "2025-01-01T00:00:00Z",
      "created_at": "2024-12-01T10:00:00Z",
      "created_by": "admin@example.com"
    }
  ]
}
```

### Rate Limit Override erstellen

```http
POST /api/v1/admin/rate-limits
```

**Request Body:**
```json
{
  "user_id": "uuid",
  "limit_type": "api",
  "requests_per_minute": 500,
  "valid_until": "2025-01-01T00:00:00Z",
  "reason": "Premium Support Anforderung"
}
```

### Rate Limit Override loeschen

```http
DELETE /api/v1/admin/rate-limits/{override_id}
```

## System Health

### System Status

```http
GET /api/v1/admin/system/status
```

**Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "components": {
    "database": {"status": "healthy", "latency_ms": 5},
    "redis": {"status": "healthy", "latency_ms": 2},
    "minio": {"status": "healthy", "latency_ms": 15},
    "celery": {"status": "healthy", "workers": 4},
    "gpu": {"status": "healthy", "vram_used_percent": 45.2}
  },
  "metrics": {
    "total_users": 150,
    "active_users_24h": 42,
    "documents_processed_24h": 1250,
    "ocr_success_rate": 0.98
  }
}
```

### Celery Queue Status

```http
GET /api/v1/admin/system/queues
```

**Response:**
```json
{
  "queues": {
    "celery": {"length": 5, "workers": 2},
    "ocr_high": {"length": 0, "workers": 1},
    "ocr_normal": {"length": 12, "workers": 2},
    "embeddings": {"length": 3, "workers": 1}
  },
  "stuck_tasks": [],
  "total_workers": 6
}
```

## Audit Logs

### Audit Logs abfragen

```http
GET /api/v1/admin/audit-logs
```

**Query Parameter:**
| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| page | int | 1 | Seitennummer |
| limit | int | 100 | Eintraege pro Seite |
| user_id | uuid | - | Nach Benutzer filtern |
| action | string | - | Nach Aktion filtern |
| from_date | datetime | - | Startdatum |
| to_date | datetime | - | Enddatum |

**Response:**
```json
{
  "total": 5000,
  "page": 1,
  "logs": [
    {
      "id": "uuid",
      "timestamp": "2024-12-02T10:30:00Z",
      "user_id": "uuid",
      "user_email": "user@example.com",
      "action": "document.delete",
      "resource_type": "document",
      "resource_id": "uuid",
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "details": {
        "filename": "vertrag.pdf",
        "reason": "user_request"
      }
    }
  ]
}
```

## Backup & Recovery

### Backup Status

```http
GET /api/v1/admin/backup/status
```

**Response:**
```json
{
  "last_backup": {
    "id": "uuid",
    "type": "full",
    "status": "completed",
    "started_at": "2024-12-02T02:30:00Z",
    "completed_at": "2024-12-02T02:45:00Z",
    "size_bytes": 10737418240
  },
  "next_scheduled": "2024-12-03T02:30:00Z",
  "storage_used_bytes": 53687091200,
  "retention_days": 30
}
```

### Manuelles Backup ausloesen

```http
POST /api/v1/admin/backup/trigger
```

**Request Body:**
```json
{
  "type": "full",
  "components": ["postgres", "minio", "redis"],
  "notify_on_complete": true
}
```

## Feature Flags

### Feature Flags auflisten

```http
GET /api/v1/admin/feature-flags
```

**Response:**
```json
{
  "flags": [
    {
      "id": "uuid",
      "key": "new_ocr_pipeline",
      "name": "Neue OCR Pipeline",
      "enabled": true,
      "rollout_percentage": 50,
      "target_tiers": ["premium"],
      "starts_at": "2024-12-01T00:00:00Z",
      "ends_at": null
    }
  ]
}
```

### Feature Flag erstellen/aktualisieren

```http
PUT /api/v1/admin/feature-flags/{key}
```

**Request Body:**
```json
{
  "name": "Neue OCR Pipeline",
  "enabled": true,
  "rollout_percentage": 75,
  "target_tiers": ["premium", "admin"],
  "target_users": ["uuid1", "uuid2"],
  "variants": {
    "control": 50,
    "variant_a": 50
  }
}
```

## Error Codes

| Code | Beschreibung |
|------|--------------|
| 401 | Nicht authentifiziert |
| 403 | Keine Admin-Berechtigung |
| 404 | Ressource nicht gefunden |
| 409 | Konflikt (z.B. E-Mail existiert bereits) |
| 422 | Validierungsfehler |
| 500 | Interner Serverfehler |

## Rate Limits

Admin-Endpoints haben erhoehte Rate Limits:
- Standard: 1000 Requests/Minute
- Bulk-Operationen: 100 Requests/Minute
- Audit-Log Abfragen: 60 Requests/Minute
