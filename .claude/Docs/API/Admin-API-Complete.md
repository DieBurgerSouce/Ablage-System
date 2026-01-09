# Admin API Documentation

> **Enterprise Administration API**
>
> Vollständige Dokumentation aller Admin-Endpoints für Systemverwaltung, Benutzermanagement und Operations.

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [User Management](#2-user-management)
3. [Role & Permission Management](#3-role--permission-management)
4. [System Status](#4-system-status)
5. [Job & Task Management](#5-job--task-management)
6. [Audit Logs](#6-audit-logs)
7. [Rate Limit Management](#7-rate-limit-management)
8. [Backup Management](#8-backup-management)
9. [Queue & Worker Management](#9-queue--worker-management)
10. [Dead Letter Queue (DLQ)](#10-dead-letter-queue-dlq)
11. [Incident Response](#11-incident-response)
12. [OCR Training Administration](#12-ocr-training-administration)
13. [ERP Connection Management](#13-erp-connection-management)
14. [Security & Permissions](#14-security--permissions)

---

## 1. Übersicht

### Endpoint-Statistiken

| Kategorie | Endpoints | Rate Limited |
|-----------|-----------|--------------|
| User Management | 6 | ✓ (Bulk Ops) |
| Roles & Permissions | 8 | ✓ |
| System Status | 5 | - |
| Jobs & Tasks | 5 | ✓ (Cancel) |
| Audit Logs | 3 | - |
| Rate Limits | 5 | ✓ |
| Backup | 16 | ✓ (Destructive) |
| Queues | 4 | - |
| DLQ | 5 | ✓ (Purge) |
| Incidents | 9 | ✓ |
| **Total** | **~80+** | |

### Authentifizierung

Alle Admin-Endpoints erfordern:
- JWT Bearer Token
- `is_superuser = true` ODER `require_admin` Role

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Destructive Operations Rate Limits

Gefährliche Operationen haben spezielle Rate Limits:

```python
# Rate Limits für destruktive Admin-Operationen
check_destructive_admin_rate_limit:
  - 10 Requests pro Minute
  - 50 Requests pro Stunde
```

---

## 2. User Management

**Basis-URL**: `/api/v1/admin/users`

### 2.1 Users auflisten

**GET** `/api/v1/admin/users`

```http
GET /api/v1/admin/users?skip=0&limit=20&status_filter=active
Authorization: Bearer <token>
```

```json
// Response 200
{
  "users": [
    {
      "id": "user-uuid",
      "email": "max@example.com",
      "username": "max.mustermann",
      "is_active": true,
      "is_superuser": false,
      "created_at": "2025-01-01T12:00:00Z",
      "last_login": "2025-01-09T08:00:00Z",
      "roles": ["user", "document_manager"]
    }
  ],
  "total": 156,
  "skip": 0,
  "limit": 20
}
```

### 2.2 User Details

**GET** `/api/v1/admin/users/{user_id}`

```json
// Response 200
{
  "id": "user-uuid",
  "email": "max@example.com",
  "username": "max.mustermann",
  "full_name": "Max Mustermann",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-09T10:00:00Z",
  "last_login": "2025-01-09T08:00:00Z",
  "roles": [
    {
      "id": "role-uuid",
      "name": "document_manager",
      "permissions": ["document:read", "document:write"]
    }
  ],
  "stats": {
    "documents_uploaded": 234,
    "ocr_requests": 1567
  }
}
```

### 2.3 User erstellen

**POST** `/api/v1/admin/users`

```json
// Request
{
  "email": "neu@example.com",
  "username": "neu.user",
  "password": "SecureP@ssw0rd!",
  "full_name": "Neuer User",
  "is_active": true,
  "is_superuser": false,
  "role_ids": ["role-uuid-1", "role-uuid-2"]
}

// Response 201
{
  "id": "new-user-uuid",
  "email": "neu@example.com",
  "username": "neu.user",
  "created_at": "2025-01-09T12:00:00Z"
}
```

### 2.4 User aktualisieren

**PUT** `/api/v1/admin/users/{user_id}`

```json
// Request (partial update)
{
  "is_active": false,
  "role_ids": ["role-uuid-1"]
}

// Response 200
{ /* Updated user */ }
```

### 2.5 User löschen

**DELETE** `/api/v1/admin/users/{user_id}`

```
Response: 204 No Content
```

**Side Effects**:
- User-Sessions werden invalidiert
- Audit-Log Eintrag
- GDPR Soft-Delete (deleted_at gesetzt)

### 2.6 Bulk Delete

**DELETE** `/api/v1/admin/users/bulk`

**Rate Limit**: `check_destructive_admin_rate_limit`

```json
// Request
{
  "user_ids": ["uuid-1", "uuid-2", "uuid-3"],
  "confirm": true  // Erforderlich!
}

// Response 200
{
  "deleted": 3,
  "failed": 0,
  "errors": []
}
```

---

## 3. Role & Permission Management

**Basis-URL**: `/api/v1/admin/roles`

### 3.1 Roles auflisten

**GET** `/api/v1/admin/roles`

```json
// Response 200
{
  "roles": [
    {
      "id": "role-uuid",
      "name": "document_manager",
      "description": "Kann Dokumente verwalten",
      "permissions": [
        {
          "id": "perm-uuid",
          "name": "document:read",
          "description": "Dokumente lesen"
        },
        {
          "id": "perm-uuid-2",
          "name": "document:write",
          "description": "Dokumente bearbeiten"
        }
      ],
      "user_count": 45
    }
  ],
  "total": 8
}
```

### 3.2 Role erstellen

**POST** `/api/v1/admin/roles`

```json
// Request
{
  "name": "ocr_specialist",
  "description": "OCR-Spezialisten mit Training-Zugriff",
  "permission_ids": ["perm-1", "perm-2"]
}

// Response 201
{ /* Created role */ }
```

### 3.3 Permission zuweisen

**POST** `/api/v1/admin/roles/{role_id}/permissions`

```json
// Request
{
  "permission_id": "perm-uuid"
}

// Response 200
{ /* Updated role with new permission */ }
```

### 3.4 Permission entfernen

**DELETE** `/api/v1/admin/roles/{role_id}/permissions/{permission_id}`

```
Response: 204 No Content
```

### 3.5 Alle Permissions auflisten

**GET** `/api/v1/admin/permissions`

```json
// Response 200
{
  "permissions": [
    {
      "id": "perm-uuid",
      "name": "document:read",
      "description": "Dokumente lesen",
      "category": "document"
    },
    {
      "id": "perm-uuid-2",
      "name": "ocr:process",
      "description": "OCR-Verarbeitung starten",
      "category": "ocr"
    }
  ]
}
```

---

## 4. System Status

**Basis-URL**: `/api/v1/admin/system`

### 4.1 Health Check

**GET** `/api/v1/admin/system/health`

```json
// Response 200
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 2
    },
    "minio": {
      "status": "healthy",
      "latency_ms": 15
    },
    "gpu": {
      "status": "healthy",
      "vram_percent": 45
    }
  },
  "timestamp": "2025-01-09T12:00:00Z"
}
```

### 4.2 System Info

**GET** `/api/v1/admin/system/info`

```json
// Response 200
{
  "version": "1.0.0",
  "environment": "production",
  "python_version": "3.11.5",
  "uptime_seconds": 86400,
  "capabilities": {
    "gpu_available": true,
    "ocr_backends": ["deepseek", "got_ocr", "surya"],
    "vector_db": "pgvector"
  },
  "config": {
    "max_upload_size_mb": 50,
    "ocr_batch_size": 4
  }
}
```

### 4.3 GPU Status

**GET** `/api/v1/admin/system/gpu`

```json
// Response 200
{
  "available": true,
  "device_name": "NVIDIA GeForce RTX 4080",
  "driver_version": "535.104.05",
  "cuda_version": "12.2",
  "memory": {
    "total_gb": 16.0,
    "used_gb": 7.2,
    "free_gb": 8.8,
    "percent": 45
  },
  "temperature_celsius": 52,
  "power_watts": 180,
  "utilization_percent": 35
}
```

### 4.4 Disk Usage

**GET** `/api/v1/admin/system/disk`

```json
// Response 200
{
  "root": {
    "total_gb": 500,
    "used_gb": 234,
    "free_gb": 266,
    "percent": 47
  },
  "backup_dir": {
    "total_gb": 1000,
    "used_gb": 156,
    "free_gb": 844,
    "percent": 16
  }
}
```

### 4.5 Database Stats

**GET** `/api/v1/admin/system/db-stats`

```json
// Response 200
{
  "connections": {
    "active": 15,
    "idle": 5,
    "max": 50
  },
  "queries": {
    "total": 1234567,
    "avg_time_ms": 12
  },
  "tables": {
    "documents": 45678,
    "users": 156,
    "rag_chunks": 234567
  }
}
```

---

## 5. Job & Task Management

**Basis-URL**: `/api/v1/admin/jobs`

### 5.1 Jobs auflisten

**GET** `/api/v1/admin/jobs`

```json
// Query Parameters
?status=processing&type=ocr&limit=50

// Response 200
{
  "jobs": [
    {
      "id": "job-uuid",
      "type": "ocr_batch",
      "status": "processing",
      "progress": 45,
      "total_items": 100,
      "processed_items": 45,
      "started_at": "2025-01-09T12:00:00Z",
      "user_id": "user-uuid"
    }
  ],
  "total": 12
}
```

### 5.2 Job Details

**GET** `/api/v1/admin/jobs/{job_id}`

```json
// Response 200
{
  "id": "job-uuid",
  "type": "ocr_batch",
  "status": "completed",
  "progress": 100,
  "result": {
    "processed": 100,
    "failed": 2,
    "errors": [
      {"document_id": "doc-1", "error": "OCR timeout"}
    ]
  },
  "started_at": "2025-01-09T12:00:00Z",
  "completed_at": "2025-01-09T12:15:00Z"
}
```

### 5.3 Job abbrechen

**POST** `/api/v1/admin/jobs/{job_id}/cancel`

**Rate Limit**: `check_destructive_admin_rate_limit`

```json
// Response 200
{
  "id": "job-uuid",
  "status": "cancelled",
  "message": "Job erfolgreich abgebrochen"
}
```

### 5.4 Bulk Cancel

**POST** `/api/v1/admin/jobs/bulk/cancel`

**Rate Limit**: `check_destructive_admin_rate_limit`

```json
// Request
{
  "job_ids": ["job-1", "job-2"],
  "confirm": true
}

// Response 200
{
  "cancelled": 2,
  "failed": 0
}
```

### 5.5 Job Statistiken

**GET** `/api/v1/admin/jobs/stats`

```json
// Response 200
{
  "total_jobs": 12456,
  "by_status": {
    "pending": 5,
    "processing": 12,
    "completed": 12300,
    "failed": 139
  },
  "by_type": {
    "ocr_batch": 8000,
    "embedding_sync": 3000,
    "backup": 1456
  },
  "avg_duration_seconds": 125
}
```

---

## 6. Audit Logs

**Basis-URL**: `/api/v1/admin/audit`

### 6.1 Audit Logs auflisten

**GET** `/api/v1/admin/audit`

```json
// Query Parameters
?user_id=uuid&action=delete&resource_type=document
&date_from=2025-01-01&date_to=2025-01-09
&impact=high&limit=100

// Response 200
{
  "logs": [
    {
      "id": "log-uuid",
      "user_id": "user-uuid",
      "username": "admin",
      "action": "delete",
      "resource_type": "document",
      "resource_id": "doc-uuid",
      "impact": "high",
      "details": {
        "document_name": "Rechnung-2025.pdf"
      },
      "ip_address": "192.168.1.100",
      "timestamp": "2025-01-09T12:00:00Z"
    }
  ],
  "total": 456
}
```

### 6.2 Einzelnen Log-Eintrag

**GET** `/api/v1/admin/audit/{log_id}`

```json
// Response 200
{
  "id": "log-uuid",
  "user_id": "user-uuid",
  "action": "delete",
  "resource_type": "document",
  "resource_id": "doc-uuid",
  "impact": "high",
  "details": { /* vollständige Details */ },
  "before_state": { /* Zustand vorher */ },
  "after_state": null,
  "request_headers": { /* gefiltert */ },
  "timestamp": "2025-01-09T12:00:00Z"
}
```

### 6.3 Audit Export

**GET** `/api/v1/admin/audit/export`

```http
GET /api/v1/admin/audit/export?format=csv&date_from=2025-01-01
Authorization: Bearer <token>

Response: Binary file (application/csv or application/json)
```

---

## 7. Rate Limit Management

**Basis-URL**: `/api/v1/admin/rate-limits`

### 7.1 Rate Limits auflisten

**GET** `/api/v1/admin/rate-limits`

```json
// Response 200
{
  "limits": [
    {
      "id": "limit-uuid",
      "name": "ocr_requests",
      "endpoint_pattern": "/api/v1/ocr/*",
      "requests_per_minute": 10,
      "requests_per_hour": 100,
      "enabled": true
    }
  ]
}
```

### 7.2 Rate Limit aktualisieren

**PUT** `/api/v1/admin/rate-limits/{limit_id}`

```json
// Request
{
  "requests_per_minute": 20,
  "requests_per_hour": 200
}

// Response 200
{ /* Updated limit */ }
```

### 7.3 User-Limits zurücksetzen

**POST** `/api/v1/admin/rate-limits/user/{user_id}/reset`

```json
// Response 200
{
  "user_id": "user-uuid",
  "reset": true,
  "message": "Rate limits für User zurückgesetzt"
}
```

### 7.4 IP Whitelist

**POST** `/api/v1/admin/rate-limits/whitelist`

```json
// Request
{
  "ip_address": "192.168.1.0/24",
  "reason": "Internes Netzwerk"
}

// Response 201
{
  "ip": "192.168.1.0/24",
  "whitelisted": true
}
```

---

## 8. Backup Management

**Basis-URL**: `/api/v1/backup`

### 8.1 Backup Status

**GET** `/api/v1/backup/status`

```json
// Response 200
{
  "status": "healthy",
  "last_backup": {
    "type": "full",
    "timestamp": "2025-01-09T02:30:00Z",
    "size_gb": 12.5,
    "duration_minutes": 15
  },
  "next_scheduled": "2025-01-10T02:30:00Z",
  "storage": {
    "local_used_gb": 156,
    "remote_used_gb": 145
  }
}
```

### 8.2 Backups auflisten

**GET** `/api/v1/backup/list`

```json
// Response 200
{
  "backups": [
    {
      "id": "backup-uuid",
      "type": "full",
      "components": ["postgres", "redis", "minio", "config"],
      "size_bytes": 13421772800,
      "created_at": "2025-01-09T02:30:00Z",
      "encrypted": true,
      "verified": true
    }
  ]
}
```

### 8.3 Komponenten-Backups

**Einzelne Komponenten**:

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/backup/postgres` | POST | PostgreSQL pg_dump |
| `/backup/redis` | POST | Redis BGSAVE |
| `/backup/minio` | POST | MinIO mc mirror |
| `/backup/config` | POST | Config tar.gz |

```json
// Response 200
{
  "component": "postgres",
  "backup_path": "/backups/postgres/2025-01-09_123000.sql.gz",
  "size_bytes": 1234567890,
  "duration_seconds": 45
}
```

### 8.4 Full Backup

**POST** `/api/v1/backup/full`

```json
// Request (optional)
{
  "encrypt": true,
  "compress": true
}

// Response 200
{
  "backup_id": "backup-uuid",
  "components": ["postgres", "redis", "minio", "config"],
  "total_size_bytes": 13421772800,
  "duration_seconds": 900
}
```

### 8.5 Async Full Backup

**POST** `/api/v1/backup/full/async`

```json
// Response 202
{
  "job_id": "job-uuid",
  "status": "started",
  "estimated_duration_minutes": 15
}
```

### 8.6 Retention anwenden

**POST** `/api/v1/backup/retention`

```json
// Request
{
  "keep_daily": 7,
  "keep_weekly": 4,
  "keep_monthly": 12,
  "dry_run": false
}

// Response 200
{
  "deleted": 15,
  "freed_bytes": 156789012345,
  "retained": 23
}
```

### 8.7 Remote Sync

**POST** `/api/v1/backup/sync`

```json
// Response 200
{
  "synced_files": 5,
  "total_bytes": 13421772800,
  "duration_seconds": 120
}
```

### 8.8 Restore Operations

**⚠️ DESTRUCTIVE OPERATIONS**

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/backup/restore/postgres` | POST | PostgreSQL Restore |
| `/backup/restore/redis` | POST | Redis Restore |
| `/backup/restore/minio` | POST | MinIO Restore |
| `/backup/restore/full` | POST | Vollständiger Restore |

```json
// Request
{
  "backup_id": "backup-uuid",
  "dry_run": true,  // Empfohlen: Erst Dry-Run!
  "confirm": true   // Erforderlich für echten Restore
}

// Response 200
{
  "restored": true,
  "components": ["postgres"],
  "duration_seconds": 120,
  "warnings": []
}
```

### 8.9 Backup Validierung

**POST** `/api/v1/backup/validate`

```json
// Request
{
  "backup_id": "backup-uuid",
  "level": "standard"  // quick|standard|deep|full
}

// Response 200
{
  "valid": true,
  "checks": {
    "integrity": "passed",
    "encryption": "passed",
    "size": "passed"
  },
  "duration_seconds": 30
}
```

---

## 9. Queue & Worker Management

**Basis-URL**: `/api/v1/admin/queues`

### 9.1 Queues auflisten

**GET** `/api/v1/admin/queues`

```json
// Response 200
{
  "queues": [
    {
      "name": "ocr_high",
      "priority": 9,
      "length": 5,
      "consumers": 2
    },
    {
      "name": "ocr_normal",
      "priority": 5,
      "length": 45,
      "consumers": 2
    },
    {
      "name": "dlq",
      "priority": 0,
      "length": 12,
      "consumers": 0
    }
  ]
}
```

**Queue Prioritäten**:

| Queue | Priority | Beschreibung |
|-------|----------|--------------|
| `ocr_high` | 9 | Prioritäts-OCR |
| `embedding_high` | 8 | Prioritäts-Embeddings |
| `ocr_normal` | 5 | Standard-OCR |
| `embedding_normal` | 5 | Standard-Embeddings |
| `validation` | 3 | Validierung |
| `metadata` | 3 | Metadaten |
| `embedding_low` | 2 | Low-Priority Embeddings |
| `backup` | 2 | Backups |
| `maintenance` | 1 | Wartung |
| `metrics` | 1 | Metriken |
| `dlq` | 0 | Dead Letter Queue |

### 9.2 Queue Stats

**GET** `/api/v1/admin/queues/{queue_name}/stats`

```json
// Response 200
{
  "queue_name": "ocr_normal",
  "stats": {
    "messages_total": 12456,
    "messages_pending": 45,
    "messages_active": 2,
    "avg_wait_time_seconds": 12,
    "throughput_per_hour": 345,
    "failure_rate": 0.02
  }
}
```

### 9.3 Workers auflisten

**GET** `/api/v1/admin/queues/workers`

```json
// Response 200
{
  "workers": [
    {
      "id": "celery@worker-1",
      "status": "active",
      "queues": ["ocr_high", "ocr_normal"],
      "concurrency": 1,
      "pool": "solo",
      "active_tasks": 1,
      "processed_total": 12456,
      "uptime_seconds": 86400
    }
  ]
}
```

### 9.4 Worker Health

**GET** `/api/v1/admin/queues/workers/health`

```json
// Response 200
{
  "healthy": true,
  "workers": {
    "total": 2,
    "active": 2,
    "offline": 0
  },
  "issues": [],
  "stuck_tasks": []
}
```

---

## 10. Dead Letter Queue (DLQ)

**Basis-URL**: `/api/v1/admin/dlq`

### 10.1 DLQ Stats

**GET** `/api/v1/admin/dlq/stats`

```json
// Response 200
{
  "status": "warning",  // healthy|warning|critical
  "total_tasks": 125,
  "by_error_type": {
    "timeout": 45,
    "gpu_oom": 30,
    "validation_error": 50
  },
  "oldest_task": "2025-01-05T12:00:00Z",
  "thresholds": {
    "healthy": 100,
    "warning": 500,
    "critical": 1000
  }
}
```

### 10.2 DLQ Tasks auflisten

**GET** `/api/v1/admin/dlq/tasks`

```json
// Query Parameters
?error_type=timeout&limit=50

// Response 200
{
  "tasks": [
    {
      "id": "task-uuid",
      "name": "ocr.process_document",
      "args": ["doc-uuid"],
      "error_type": "timeout",
      "error_message": "Task exceeded 300s timeout",
      "retry_count": 3,
      "failed_at": "2025-01-09T12:00:00Z",
      "original_queue": "ocr_normal"
    }
  ],
  "total": 125
}
```

### 10.3 Task Retry

**POST** `/api/v1/admin/dlq/{task_id}/retry`

```json
// Response 200
{
  "task_id": "task-uuid",
  "status": "requeued",
  "queue": "ocr_normal"
}
```

### 10.4 Bulk Retry

**POST** `/api/v1/admin/dlq/bulk/retry`

```json
// Request
{
  "task_ids": ["task-1", "task-2"],
  "error_type_filter": "timeout"  // optional: nur bestimmte Fehler
}

// Response 200
{
  "requeued": 45,
  "failed": 0
}
```

### 10.5 DLQ Purge

**POST** `/api/v1/admin/dlq/purge`

**⚠️ DESTRUCTIVE - Löscht alle fehlgeschlagenen Tasks!**

**Rate Limit**: `check_destructive_admin_rate_limit`

```json
// Request
{
  "confirm": true,  // ERFORDERLICH!
  "older_than_days": 7  // optional: nur alte Tasks
}

// Response 200
{
  "purged": 125,
  "message": "DLQ erfolgreich geleert"
}
```

---

## 11. Incident Response

**Basis-URL**: `/api/v1/admin/incidents`

### 11.1 Incidents auflisten

**GET** `/api/v1/admin/incidents`

```json
// Response 200
{
  "incidents": [
    {
      "id": "incident-uuid",
      "type": "brute_force_attempt",
      "severity": "high",
      "status": "active",
      "source_ip": "1.2.3.4",
      "details": {
        "attempts": 150,
        "target_endpoint": "/api/v1/auth/login"
      },
      "created_at": "2025-01-09T12:00:00Z"
    }
  ],
  "total": 3
}
```

### 11.2 Incident Stats

**GET** `/api/v1/admin/incidents/stats`

```json
// Response 200
{
  "total_incidents": 45,
  "by_severity": {
    "critical": 2,
    "high": 12,
    "medium": 20,
    "low": 11
  },
  "by_type": {
    "brute_force_attempt": 15,
    "rate_limit_abuse": 20,
    "suspicious_activity": 10
  },
  "blocked_ips": 5
}
```

### 11.3 Blocked IPs

**GET** `/api/v1/admin/incidents/blocked-ips`

```json
// Response 200
{
  "blocked_ips": [
    {
      "ip": "1.2.3.4",
      "reason": "Brute Force Attack",
      "blocked_at": "2025-01-09T12:00:00Z",
      "expires_at": "2025-01-16T12:00:00Z",
      "incident_id": "incident-uuid"
    }
  ]
}
```

### 11.4 IP manuell blockieren

**POST** `/api/v1/admin/incidents/blocked-ips`

```json
// Request
{
  "ip_address": "5.6.7.8",
  "reason": "Manuell blockiert wegen Spam",
  "duration_hours": 168  // 7 Tage
}

// Response 201
{
  "ip": "5.6.7.8",
  "blocked": true,
  "expires_at": "2025-01-16T12:00:00Z"
}
```

### 11.5 IP freigeben

**DELETE** `/api/v1/admin/incidents/blocked-ips/{ip_address}`

```
Response: 204 No Content
```

### 11.6 Incident schließen

**DELETE** `/api/v1/admin/incidents/{incident_id}`

```json
// Response 200
{
  "id": "incident-uuid",
  "status": "resolved",
  "resolved_at": "2025-01-09T13:00:00Z"
}
```

### 11.7 Security Config

**GET** `/api/v1/admin/incidents/config/security`

```json
// Response 200
{
  "brute_force": {
    "max_attempts": 5,
    "lockout_minutes": 15
  },
  "rate_limiting": {
    "enabled": true,
    "fail_closed": true
  },
  "ip_blocking": {
    "auto_block_threshold": 100,
    "default_block_hours": 168
  }
}
```

---

## 12. OCR Training Administration

**Basis-URL**: `/api/v1/training`

### 12.1 Training Samples

**GET** `/api/v1/training/samples`

```json
// Query Parameters
?status=pending&document_type=invoice&limit=50

// Response 200
{
  "samples": [
    {
      "id": "sample-uuid",
      "document_id": "doc-uuid",
      "status": "pending",
      "ocr_text": "Rechnungsnr: 2025-001...",
      "ground_truth": null,
      "quality_score": null
    }
  ],
  "total": 234
}
```

### 12.2 Backend Comparison

**GET** `/api/v1/training/benchmarks/compare`

```json
// Response 200
{
  "backends": {
    "deepseek": {
      "cer": 0.023,
      "wer": 0.045,
      "umlaut_accuracy": 0.98,
      "samples_evaluated": 1000
    },
    "got_ocr": {
      "cer": 0.035,
      "wer": 0.067,
      "umlaut_accuracy": 0.92,
      "samples_evaluated": 1000
    }
  },
  "winner": "deepseek"
}
```

### 12.3 Training Stats

**GET** `/api/v1/training/stats/overview`

```json
// Response 200
{
  "total_samples": 5678,
  "verified_samples": 4500,
  "pending_samples": 1178,
  "by_document_type": {
    "invoice": 3000,
    "contract": 1500,
    "other": 1178
  },
  "quality_distribution": {
    "excellent": 3500,
    "good": 800,
    "needs_review": 200
  }
}
```

---

## 13. ERP Connection Management

**Basis-URL**: `/api/v1/erp`

### 13.1 Connections auflisten

**GET** `/api/v1/erp/connections`

```json
// Response 200
{
  "connections": [
    {
      "id": "conn-uuid",
      "name": "Odoo Production",
      "type": "odoo",
      "status": "connected",
      "last_sync": "2025-01-09T12:00:00Z",
      "documents_synced": 12456
    }
  ]
}
```

### 13.2 Connection testen

**POST** `/api/v1/erp/connections/{connection_id}/test`

```json
// Response 200
{
  "success": true,
  "latency_ms": 45,
  "version": "17.0",
  "capabilities": ["invoices", "orders", "customers"]
}
```

### 13.3 Sync triggern

**POST** `/api/v1/erp/connections/{connection_id}/sync`

```json
// Request
{
  "sync_type": "delta",  // full|delta
  "entity_types": ["invoices"]  // optional
}

// Response 202
{
  "job_id": "job-uuid",
  "status": "started"
}
```

### 13.4 Sync History

**GET** `/api/v1/erp/connections/{connection_id}/sync/history`

```json
// Response 200
{
  "syncs": [
    {
      "id": "sync-uuid",
      "type": "delta",
      "status": "completed",
      "entities_synced": 45,
      "errors": 0,
      "started_at": "2025-01-09T12:00:00Z",
      "completed_at": "2025-01-09T12:01:00Z"
    }
  ]
}
```

### 13.5 Conflicts

**GET** `/api/v1/erp/conflicts`

```json
// Response 200
{
  "conflicts": [
    {
      "id": "conflict-uuid",
      "entity_type": "invoice",
      "entity_id": "inv-123",
      "local_value": { /* ... */ },
      "remote_value": { /* ... */ },
      "created_at": "2025-01-09T12:00:00Z"
    }
  ]
}
```

### 13.6 Conflict auflösen

**POST** `/api/v1/erp/conflicts/{conflict_id}/resolve`

```json
// Request
{
  "resolution": "use_local"  // use_local|use_remote|merge
}

// Response 200
{
  "id": "conflict-uuid",
  "status": "resolved",
  "resolution": "use_local"
}
```

---

## 14. Security & Permissions

### 14.1 Permission Dependencies

```python
# app/api/dependencies.py

# Basis-Auth
get_current_user() -> User
get_current_active_user() -> User

# Admin-Auth
get_current_superuser() -> User  # is_superuser=True
require_admin() -> User          # Admin Role

# Rate Limiting
check_rate_limit(request, user)
check_destructive_admin_rate_limit(request, admin)
```

### 14.2 Permission Checks

```python
# User muss Superuser sein
@router.get("/admin/users")
async def list_users(
    admin: User = Depends(get_current_superuser)
):
    ...

# Destruktive Operation mit Rate Limit
@router.delete("/admin/users/bulk")
async def bulk_delete(
    admin: User = Depends(get_current_superuser),
    _: None = Depends(check_destructive_admin_rate_limit)
):
    ...
```

### 14.3 Audit Logging

Alle Admin-Operationen werden geloggt:

```python
logger.info(
    "admin_operation",
    admin_id=str(admin.id),
    resource_type="user",
    resource_id=str(user.id),
    action="deleted",
    impact="high"
)
```

**Destruktive Operationen** werden als WARNING geloggt:
- DLQ Purge
- User Deletion
- Backup Deletion
- IP Unblocking

### 14.4 Security Fixes

| Fix | Beschreibung |
|-----|--------------|
| Z.2 | Path Traversal Protection für Backups |
| K.4 | RLS Context Validation |
| Q.1 | Active User Check in Auth |
| P.2 | GDPR Soft-Delete Compliance |
| L.1 | Fail-Closed Rate Limiting |
| K.1 | Homoglyph Normalization |

---

## Error Responses

### Standard Error Format

```json
{
  "detail": "Fehler-Meldung auf Deutsch",
  "status_code": 400,
  "timestamp": "2025-01-09T12:00:00Z"
}
```

### Common Status Codes

| Code | Beschreibung |
|------|--------------|
| 401 | Nicht authentifiziert |
| 403 | Keine Admin-Berechtigung |
| 404 | Resource nicht gefunden |
| 429 | Rate Limit überschritten |
| 503 | Service nicht verfügbar |

---

**Letzte Aktualisierung**: Januar 2026
**Version**: 1.0
**Maintainer**: Ablage-System Team
