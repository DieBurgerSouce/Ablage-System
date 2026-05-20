# Configuration Reference - Ablage-System OCR

> Vollstaendige Dokumentation aller Konfigurationsoptionen

## Uebersicht

Das Ablage-System wird ueber Umgebungsvariablen konfiguriert. Diese koennen in einer `.env` Datei oder direkt als Umgebungsvariablen gesetzt werden.

**Konfigurationsdatei:** `.env` im Projektverzeichnis

```bash
# .env aus Template erstellen
cp .env.example .env
```

---

## Pflichtfelder (REQUIRED)

Diese Variablen MUESSEN gesetzt werden:

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `SECRET_KEY` | JWT Secret Key (min. 32 Zeichen) | `openssl rand -hex 32` |
| `DB_PASSWORD` | PostgreSQL Passwort | Sicheres Passwort |
| `MINIO_ACCESS_KEY` | MinIO Access Key | `ablage_admin` |
| `MINIO_SECRET_KEY` | MinIO Secret Key | Sicheres Passwort |

---

## Kategorien

### Application

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `APP_NAME` | string | `Ablage-System OCR` | Anwendungsname |
| `APP_VERSION` | string | `1.0.0` | Version |
| `API_V1_PREFIX` | string | `/api/v1` | API Prefix |
| `DEBUG` | bool | `false` | Debug-Modus |

### Server

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `API_HOST` | string | `0.0.0.0` | Bind Address |
| `API_PORT` | int | `8000` | Port |
| `API_RELOAD` | bool | `false` | Hot-Reload (Development) |

### Logging

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `LOG_LEVEL` | string | `INFO` | Log Level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | string | `json` | Format (json/text) |

### Security

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `SECRET_KEY` | string | **REQUIRED** | JWT Secret Key |
| `ENCRYPTION_KEY` | string | aus SECRET_KEY | AES-256 Key (Base64) |
| `ALGORITHM` | string | `HS256` | JWT Algorithmus |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `15` | Access Token Lebensdauer |
| `REFRESH_TOKEN_EXPIRE_DAYS` | int | `7` | Refresh Token Lebensdauer |

### CORS

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `CORS_ORIGINS` | list | `["http://localhost:3000"]` | Erlaubte Origins |
| `CORS_ALLOW_CREDENTIALS` | bool | `true` | Credentials erlauben |
| `CORS_ALLOW_METHODS` | list | `["GET","POST",...]` | Erlaubte Methods |
| `CORS_ALLOW_HEADERS` | list | `["Authorization",...]` | Erlaubte Headers |
| `CORS_MAX_AGE` | int | `600` | Preflight Cache (Sekunden) |

### Database (PostgreSQL)

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `DB_USER` | string | `ablage_admin` | Benutzername |
| `DB_PASSWORD` | string | **REQUIRED** | Passwort |
| `DB_HOST` | string | `localhost` | Host |
| `DB_PORT` | int | `5433` | Port |
| `DB_NAME` | string | `ablage_system` | Datenbankname |
| `DATABASE_URL` | string | - | Vollstaendige URL (ueberschreibt obige) |

#### Connection Pool

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `DB_POOL_SIZE` | int | `50` | Pool-Groesse (API) |
| `DB_MAX_OVERFLOW` | int | `150` | Max Overflow |
| `DB_POOL_RECYCLE` | int | `1800` | Recycle-Zeit (Sekunden) |
| `DB_POOL_TIMEOUT` | int | `10` | Verbindungs-Timeout |
| `DB_POOL_PRE_PING` | bool | `true` | Verbindung vor Nutzung pruefen |

### Redis

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `REDIS_HOST` | string | `localhost` | Host |
| `REDIS_PORT` | int | `6380` | Port |
| `REDIS_DB` | int | `0` | Datenbank-Index |
| `REDIS_PASSWORD` | string | - | Passwort (optional) |
| `REDIS_URL` | string | - | Vollstaendige URL |

### Celery

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `CELERY_BROKER_URL` | string | Redis URL | Broker URL |
| `CELERY_RESULT_BACKEND` | string | Redis URL | Result Backend |
| `CELERY_TASK_ALWAYS_EAGER` | bool | `false` | Sync-Modus (Testing) |

### MinIO (Object Storage)

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `MINIO_ENDPOINT` | string | `localhost:9000` | Endpoint |
| `MINIO_ACCESS_KEY` | string | **REQUIRED** | Access Key |
| `MINIO_SECRET_KEY` | string | **REQUIRED** | Secret Key |
| `MINIO_SECURE` | bool | `false` | HTTPS verwenden |
| `MINIO_BUCKET_DOCUMENTS` | string | `documents` | Dokumente-Bucket |
| `MINIO_BUCKET_PROCESSED` | string | `processed` | Verarbeitete-Bucket |
| `MINIO_BUCKET_THUMBNAILS` | string | `thumbnails` | Thumbnails-Bucket |

### File Upload

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `MAX_UPLOAD_SIZE_MB` | int | `50` | Max. Dateigroesse (MB) |
| `ALLOWED_EXTENSIONS` | list | `[".pdf",".png",...]` | Erlaubte Dateitypen |
| `UPLOAD_DIR` | path | `/app/uploads` | Upload-Verzeichnis |
| `OUTPUT_DIR` | path | `/app/outputs` | Output-Verzeichnis |

### OCR Settings

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `DEFAULT_OCR_BACKEND` | string | `auto` | Standard-Backend |
| `DEFAULT_LANGUAGE` | string | `de` | Standard-Sprache |
| `OCR_TIMEOUT_SECONDS` | int | `300` | Timeout (5 Min) |
| `MAX_PAGES_PER_DOCUMENT` | int | `100` | Max. Seiten |

### GPU Settings

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `CUDA_VISIBLE_DEVICES` | string | `0` | GPU-Index |
| `GPU_ENABLED` | bool | `true` | GPU aktivieren |
| `MAX_GPU_MEMORY_PERCENT` | int | `85` | Max. VRAM-Nutzung (%) |
| `GPU_LOCK_TIMEOUT` | int | `180` | Lock-Timeout (Sekunden) |
| `MAX_BATCH_SIZE` | int | `8` | Max. Batch-Groesse |

### Rate Limiting

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `RATE_LIMIT_ENABLED` | bool | `true` | Rate Limiting aktivieren |
| `RATE_LIMIT_FAIL_CLOSED` | bool | `true` | Bei Redis-Ausfall blockieren |
| `RATE_LIMIT_FREE_OCR_PER_HOUR` | int | `10` | OCR/Stunde (Free) |
| `RATE_LIMIT_FREE_OCR_PER_DAY` | int | `50` | OCR/Tag (Free) |
| `RATE_LIMIT_PREMIUM_OCR_PER_HOUR` | int | `100` | OCR/Stunde (Premium) |
| `RATE_LIMIT_PREMIUM_OCR_PER_DAY` | int | `1000` | OCR/Tag (Premium) |

### Email (SMTP)

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `SMTP_HOST` | string | - | SMTP Server |
| `SMTP_PORT` | int | `587` | SMTP Port |
| `SMTP_USER` | string | - | Benutzername |
| `SMTP_PASSWORD` | string | - | Passwort |
| `SMTP_FROM_EMAIL` | string | - | Absender-Email |
| `SMTP_TLS` | bool | `true` | TLS verwenden |

### Backup

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `BACKUP_ENABLED` | bool | `true` | Backups aktivieren |
| `BACKUP_DIR` | path | `/app/backups` | Backup-Verzeichnis |
| `BACKUP_RETENTION_DAYS` | int | `30` | Aufbewahrungsdauer |
| `BACKUP_REMOTE_ENABLED` | bool | `false` | Remote-Sync aktivieren |
| `BACKUP_REMOTE_HOST` | string | - | Remote-Server |

### Vault (HashiCorp)

| Variable | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `VAULT_ENABLED` | bool | `false` | Vault aktivieren |
| `VAULT_URL` | string | - | Vault URL |
| `VAULT_TOKEN` | string | - | Vault Token |
| `VAULT_NAMESPACE` | string | - | Vault Namespace |

---

## Beispiel-Konfigurationen

### Development

```bash
# .env.development
DEBUG=true
LOG_LEVEL=DEBUG
API_RELOAD=true

SECRET_KEY=dev_secret_key_not_for_production_use_32chars
DB_PASSWORD=dev_password
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
```

### Production

```bash
# .env.production
DEBUG=false
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security (IMMER neu generieren!)
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())")

# Database
DB_PASSWORD=<sicheres_passwort>
DB_HOST=postgres
DB_POOL_SIZE=100

# Redis
REDIS_PASSWORD=<sicheres_passwort>
REDIS_HOST=redis

# MinIO
MINIO_ACCESS_KEY=<access_key>
MINIO_SECRET_KEY=<sicheres_passwort>
MINIO_SECURE=true

# CORS (nur Production-Domain!)
CORS_ORIGINS=["https://ablage-system.example.com"]

# GPU
GPU_ENABLED=true
MAX_GPU_MEMORY_PERCENT=85

# Backup
BACKUP_ENABLED=true
BACKUP_RETENTION_DAYS=90
```

### Testing

```bash
# .env.test
DEBUG=false
TESTING=true
CELERY_TASK_ALWAYS_EAGER=true

SECRET_KEY=test_secret_key_not_for_production_use
DB_PASSWORD=test_password
DB_NAME=ablage_test
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

GPU_ENABLED=false
```

---

## Secrets generieren

```bash
# SECRET_KEY (min. 32 Zeichen)
openssl rand -hex 32

# ENCRYPTION_KEY (Base64-encoded 32 Bytes)
python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"

# Sicheres Passwort
openssl rand -base64 24
```

---

## Umgebungsvariablen in Docker

```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DB_PASSWORD=${DB_PASSWORD}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
    env_file:
      - .env
```

---

## Vault-Integration

Fuer Produktion wird HashiCorp Vault empfohlen:

```bash
# Vault aktivieren
VAULT_ENABLED=true
VAULT_URL=https://vault.example.com:8200
VAULT_TOKEN=hvs.xxx

# Secrets werden aus Vault geladen:
# vault kv get -field=db_password secret/ablage/production
```

---

## Weitere Dokumentation

- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment-Anleitung
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Systemarchitektur
- [.env.example](../.env.example) - Template-Datei

---

*Version: 1.0 | Letzte Aktualisierung: 2024-12*
