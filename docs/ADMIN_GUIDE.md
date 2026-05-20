# Ablage-System Administrator-Handbuch

> **Version:** 1.0
> **Stand:** Januar 2025
> **Zielgruppe:** System-Administratoren und IT-Betrieb

---

## Inhaltsverzeichnis

1. [Systemübersicht](#systemübersicht)
2. [Installation](#installation)
3. [Konfiguration](#konfiguration)
4. [Benutzerverwaltung](#benutzerverwaltung)
5. [Backup & Recovery](#backup--recovery)
6. [Monitoring](#monitoring)
7. [Wartung](#wartung)
8. [Fehlerbehebung](#fehlerbehebung)
9. [Sicherheit](#sicherheit)
10. [Performance-Optimierung](#performance-optimierung)

---

## Systemübersicht

### Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Ablage-System OCR                        │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Nginx:80)     │  Grafana (:3002)  │  Prometheus  │
├──────────────────────────┴───────────────────┴──────────────┤
│                    FastAPI Backend (:8000)                  │
├─────────────────────────────────────────────────────────────┤
│  Celery Workers  │  Redis (:6380)  │  PostgreSQL (:5433)    │
├─────────────────────────────────────────────────────────────┤
│  OCR Backends: DeepSeek | GOT-OCR | Surya | Surya-GPU       │
├─────────────────────────────────────────────────────────────┤
│                 GPU: NVIDIA RTX 4080 (16GB)                 │
└─────────────────────────────────────────────────────────────┘
```

### Komponenten

| Komponente | Funktion | Port |
|------------|----------|------|
| **Backend** | FastAPI REST API | 8000 |
| **Frontend** | React Web-Anwendung | 80 (Nginx) |
| **PostgreSQL** | Hauptdatenbank | 5433 |
| **Redis** | Cache und Job-Queue | 6380 |
| **MinIO** | Objekt-Speicher (Dokumente) | 9000/9001 |
| **Celery Worker** | Asynchrone Aufgaben | - |
| **Grafana** | Monitoring Dashboard | 3002 |
| **Prometheus** | Metriken-Sammlung | 9090 |
| **Loki** | Log-Aggregation | 3100 |

### Hardware-Anforderungen

| Ressource | Minimum | Empfohlen |
|-----------|---------|-----------|
| **CPU** | 8 Cores | 16+ Cores |
| **RAM** | 32 GB | 64 GB |
| **GPU** | RTX 3080 (10GB) | RTX 4080 (16GB) |
| **Storage** | 500 GB SSD | 2 TB NVMe |
| **Netzwerk** | 1 Gbit | 10 Gbit |

---

## Installation

### Voraussetzungen

```bash
# Docker & Docker Compose
docker --version  # >= 24.0
docker-compose --version  # >= 2.20

# NVIDIA Container Toolkit (für GPU)
nvidia-smi  # CUDA >= 12.0

# Git
git --version
```

### Basis-Installation

```bash
# Repository klonen
git clone https://github.com/ihre-firma/ablage-system.git
cd ablage-system

# Umgebungsvariablen konfigurieren
cp .env.example .env
nano .env  # Konfiguration anpassen

# Container starten
docker-compose up -d

# Status prüfen
docker-compose ps
```

### Erste Schritte nach Installation

```bash
# 1. Datenbank-Migrationen ausführen
docker-compose exec backend alembic upgrade head

# 2. Admin-Benutzer erstellen
docker-compose exec backend python -m app.scripts.create_admin

# 3. System-Health prüfen
curl http://localhost:8000/api/v1/health
```

---

## Konfiguration

### Umgebungsvariablen (.env)

```bash
# Datenbank
DATABASE_URL=postgresql+asyncpg://ablage_admin:secure_password@postgres:5432/ablage
POSTGRES_USER=ablage_admin
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=ablage

# Redis
REDIS_URL=redis://:redis_password@redis:6379/0
REDIS_PASSWORD=redis_password

# MinIO (Objekt-Speicher)
MINIO_ROOT_USER=minio_admin
MINIO_ROOT_PASSWORD=minio_secure_password
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET=documents

# Sicherheit
SECRET_KEY=<generierter_sicherer_schlüssel>
JWT_SECRET=<jwt_secret_key>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# GPU
GPU_MEMORY_LIMIT=0.85
CUDA_VISIBLE_DEVICES=0

# OCR Backends
DEFAULT_OCR_BACKEND=deepseek
DEEPSEEK_MODEL_PATH=/models/deepseek-janus-pro
GOT_OCR_MODEL_PATH=/models/got-ocr-2.0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Docker-Compose Anpassungen

```yaml
# docker-compose.override.yml für lokale Anpassungen
services:
  backend:
    environment:
      - DEBUG=false
      - LOG_LEVEL=WARNING
    deploy:
      resources:
        limits:
          memory: 8G

  worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 16G
```

### Nginx-Konfiguration

```nginx
# /etc/nginx/conf.d/ablage.conf
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name ablage.ihre-firma.de;

    # Weiterleitung zu HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ablage.ihre-firma.de;

    ssl_certificate /etc/ssl/certs/ablage.crt;
    ssl_certificate_key /etc/ssl/private/ablage.key;

    # Sicherheits-Header
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Upload-Limit
    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Benutzerverwaltung

### Benutzer anlegen

```bash
# Über CLI
docker-compose exec backend python -m app.scripts.create_user \
    --email nutzer@firma.de \
    --password sicheres_passwort \
    --role user

# Admin-Benutzer
docker-compose exec backend python -m app.scripts.create_user \
    --email admin@firma.de \
    --password admin_passwort \
    --role admin
```

### API-Endpunkte für Benutzerverwaltung

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| GET | `/api/v1/admin/users` | Alle Benutzer auflisten |
| POST | `/api/v1/admin/users` | Neuen Benutzer erstellen |
| GET | `/api/v1/admin/users/{id}` | Benutzer-Details |
| PUT | `/api/v1/admin/users/{id}` | Benutzer bearbeiten |
| DELETE | `/api/v1/admin/users/{id}` | Benutzer löschen |
| POST | `/api/v1/admin/users/{id}/reset-password` | Passwort zurücksetzen |

### Rollen und Berechtigungen

| Rolle | Beschreibung | Berechtigungen |
|-------|--------------|----------------|
| **user** | Standard-Benutzer | Eigene Dokumente verwalten |
| **editor** | Erweiterter Benutzer | Dokumente bearbeiten, Tags vergeben |
| **admin** | Administrator | Vollzugriff, Benutzerverwaltung |
| **superadmin** | Super-Administrator | System-Konfiguration, Backup |

### LDAP/Active Directory Integration

```yaml
# .env
LDAP_ENABLED=true
LDAP_SERVER=ldap://ldap.ihre-firma.de:389
LDAP_BASE_DN=dc=ihre-firma,dc=de
LDAP_BIND_DN=cn=ablage-service,ou=services,dc=ihre-firma,dc=de
LDAP_BIND_PASSWORD=ldap_password
LDAP_USER_SEARCH_FILTER=(sAMAccountName={username})
LDAP_GROUP_SEARCH_FILTER=(member={user_dn})
LDAP_ADMIN_GROUP=CN=Ablage-Admins,OU=Groups,DC=ihre-firma,DC=de
```

---

## Backup & Recovery

### Automatische Backups

Das System führt automatisch tägliche Backups durch:

| Komponente | Zeitplan | Aufbewahrung |
|------------|----------|--------------|
| PostgreSQL | Täglich 02:30 | 30 Tage |
| Redis | Täglich 02:30 | 7 Tage |
| MinIO | Täglich 03:00 | 90 Tage |
| Konfiguration | Täglich 02:00 | 30 Tage |

### Manuelles Backup

```bash
# Vollständiges Backup
curl -X POST http://localhost:8000/api/v1/backup/full \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Nur PostgreSQL
docker exec ablage-postgres pg_dump \
    -U ablage_admin \
    -d ablage \
    -F c \
    -f /backup/postgres_$(date +%Y%m%d_%H%M%S).dump

# Nur MinIO
docker exec ablage-minio mc mirror local/documents /backup/minio/
```

### Backup-Status prüfen

```bash
# API-Endpunkt
curl http://localhost:8000/api/v1/backup/status

# Backup-Liste
curl http://localhost:8000/api/v1/backup/list
```

### Recovery-Verfahren

#### PostgreSQL Restore

```bash
# 1. Backend stoppen
docker-compose stop backend worker

# 2. Datenbank wiederherstellen
docker exec -i ablage-postgres pg_restore \
    -U ablage_admin \
    -d ablage \
    -c \
    < /backup/postgres_20250108.dump

# 3. Services starten
docker-compose up -d backend worker
```

#### Vollständiger Disaster Recovery

```bash
# 1. Alle Services stoppen
docker-compose down

# 2. Volumes löschen (falls korrupt)
docker volume rm ablage_postgres_data ablage_redis_data

# 3. Services neu starten (leere Volumes)
docker-compose up -d postgres redis minio

# 4. Backups einspielen
# ... (siehe einzelne Recovery-Schritte)

# 5. Migrationen anwenden
docker-compose exec backend alembic upgrade head

# 6. Alle Services starten
docker-compose up -d
```

---

## Monitoring

### Grafana-Dashboards

**Zugang:** http://localhost:3002 (admin/admin123)

Verfügbare Dashboards:

| Dashboard | Beschreibung |
|-----------|--------------|
| **Ablage Overview** | Systemübersicht, KPIs |
| **OCR Performance** | OCR-Durchsatz, Erfolgsrate |
| **GPU Monitoring** | VRAM, Temperatur, Auslastung |
| **Database Metrics** | PostgreSQL Performance |
| **Queue Status** | Celery Tasks, Warteschlange |
| **Backup Monitoring** | Backup-Status, Größen |

### Prometheus-Metriken

```bash
# Metriken-Endpunkt
curl http://localhost:8000/api/v1/metrics

# Wichtige Metriken
ocr_requests_total          # Gesamtzahl OCR-Anfragen
ocr_processing_duration     # Verarbeitungszeit
gpu_memory_usage_bytes      # GPU-Speicher
document_queue_length       # Warteschlange
api_request_duration        # API-Latenz
```

### Alerting

Vorkonfigurierte Alerts:

| Alert | Schwellwert | Aktion |
|-------|-------------|--------|
| GPUMemoryHigh | > 85% | E-Mail an Admin |
| APIErrorRateHigh | > 5% | Slack-Nachricht |
| QueueBacklog | > 100 Docs | PagerDuty |
| BackupFailed | Fehler | E-Mail + SMS |
| DiskSpaceLow | < 10% | E-Mail an Admin |

### Log-Analyse

```bash
# Backend-Logs
docker-compose logs -f backend --since 1h

# Worker-Logs (OCR)
docker-compose logs -f worker --since 1h

# Fehler filtern
docker-compose logs backend 2>&1 | grep -E "ERROR|Exception"

# Loki-Abfrage (über Grafana)
{container_name="ablage-backend"} |= "ERROR"
```

---

## Wartung

### Geplante Wartung

```bash
# 1. Wartungsmodus aktivieren
curl -X POST http://localhost:8000/api/v1/admin/maintenance/enable \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Wartungsarbeiten durchführen
# ...

# 3. Wartungsmodus deaktivieren
curl -X DELETE http://localhost:8000/api/v1/admin/maintenance/enable \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Datenbank-Wartung

```bash
# VACUUM (wöchentlich empfohlen)
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "VACUUM ANALYZE;"

# Statistiken aktualisieren
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "ANALYZE;"

# Indizes neu erstellen (selten, bei Performance-Problemen)
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "REINDEX DATABASE ablage;"
```

### Container-Updates

```bash
# 1. Neue Images herunterladen
docker-compose pull

# 2. Container neu starten (Rolling Update)
docker-compose up -d --no-deps backend
docker-compose up -d --no-deps worker
docker-compose up -d --no-deps frontend

# 3. Alte Images entfernen
docker image prune -f
```

### Cleanup-Aufgaben

```bash
# Alte Logs löschen
docker exec ablage-backend find /var/log/ablage -mtime +30 -delete

# Temporäre Dateien
docker exec ablage-backend rm -rf /tmp/ocr_*

# Gelöschte Dokumente endgültig entfernen (nach GDPR-Frist)
curl -X POST http://localhost:8000/api/v1/admin/cleanup/deleted-documents \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Redis Cache leeren (bei Problemen)
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD FLUSHDB
```

---

## Fehlerbehebung

### Häufige Probleme

#### GPU nicht erkannt

```bash
# NVIDIA-Treiber prüfen
nvidia-smi

# Container GPU-Zugriff prüfen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# NVIDIA Container Toolkit prüfen
docker info | grep -i nvidia
```

#### Datenbank-Verbindungsprobleme

```bash
# PostgreSQL-Status
docker-compose exec postgres pg_isready

# Verbindungspool prüfen
docker-compose exec postgres psql -U ablage_admin -d ablage -c \
    "SELECT count(*) FROM pg_stat_activity WHERE datname = 'ablage';"

# Langsame Queries identifizieren
docker-compose exec postgres psql -U ablage_admin -d ablage -c \
    "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

#### OCR-Verarbeitung hängt

```bash
# Worker-Status
docker-compose exec worker celery -A app.workers.celery_app inspect ping

# Aktive Tasks
docker-compose exec worker celery -A app.workers.celery_app inspect active

# Task abbrechen
docker-compose exec worker celery -A app.workers.celery_app control revoke <task_id> --terminate

# Worker neu starten
docker-compose restart worker
```

#### Speicherplatz-Probleme

```bash
# Docker-Speicher
docker system df

# Aufräumen
docker system prune -a --volumes

# MinIO-Speicher
docker exec ablage-minio mc du local/documents

# PostgreSQL-Größe
docker exec ablage-postgres psql -U ablage_admin -d ablage -c \
    "SELECT pg_size_pretty(pg_database_size('ablage'));"
```

### Runbooks

Detaillierte Anleitungen für spezifische Probleme finden Sie unter:

`.claude/Docs/Operations/Runbooks/`

- `gpu-oom-recovery.md` - GPU Out-of-Memory
- `database-recovery.md` - Datenbank-Wiederherstellung
- `celery-worker-restart.md` - Worker-Probleme
- `redis-cluster-recovery.md` - Redis-Ausfälle
- `minio-failure-recovery.md` - Objekt-Speicher-Probleme

---

## Sicherheit

### Firewall-Regeln

```bash
# Nur notwendige Ports öffnen
ufw allow 80/tcp    # HTTP (Redirect)
ufw allow 443/tcp   # HTTPS
ufw deny 8000/tcp   # Backend nur intern
ufw deny 5433/tcp   # PostgreSQL nur intern
ufw deny 6380/tcp   # Redis nur intern
```

### SSL/TLS-Konfiguration

```bash
# Zertifikat mit Let's Encrypt
certbot --nginx -d ablage.ihre-firma.de

# Selbstsigniertes Zertifikat (Entwicklung)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/ablage.key \
    -out /etc/ssl/certs/ablage.crt
```

### Sicherheits-Checkliste

- [ ] Alle Standard-Passwörter geändert
- [ ] SSL/TLS aktiviert
- [ ] Firewall konfiguriert
- [ ] Backups verschlüsselt
- [ ] LDAP/SSO integriert
- [ ] Rate-Limiting aktiviert
- [ ] Audit-Logging aktiviert
- [ ] Regelmäßige Security-Updates

### Audit-Logging

```bash
# Audit-Logs anzeigen
curl http://localhost:8000/api/v1/admin/audit-logs \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Nach Benutzer filtern
curl "http://localhost:8000/api/v1/admin/audit-logs?user_id=123" \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Nach Aktion filtern
curl "http://localhost:8000/api/v1/admin/audit-logs?action=document.delete" \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### GDPR-Compliance

```bash
# Benutzer-Daten exportieren (Art. 20)
curl "http://localhost:8000/api/v1/gdpr/export/{user_id}" \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Benutzer-Daten löschen (Art. 17)
curl -X DELETE "http://localhost:8000/api/v1/gdpr/delete/{user_id}" \
    -H "Authorization: Bearer $ADMIN_TOKEN"

# Aufbewahrungsfristen prüfen
curl "http://localhost:8000/api/v1/gdpr/retention-status" \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Performance-Optimierung

### GPU-Optimierung

```bash
# GPU-Auslastung überwachen
watch -n 1 nvidia-smi

# Batch-Größe anpassen
# .env
OCR_BATCH_SIZE=16        # Standard: 8
GPU_MEMORY_FRACTION=0.9  # Standard: 0.85

# CUDA-Cache leeren
docker exec ablage-worker python -c "import torch; torch.cuda.empty_cache()"
```

### Datenbank-Optimierung

```sql
-- Häufig genutzte Indizes
CREATE INDEX CONCURRENTLY idx_documents_created_at ON documents(created_at);
CREATE INDEX CONCURRENTLY idx_documents_status ON documents(status);
CREATE INDEX CONCURRENTLY idx_documents_user_id ON documents(user_id);

-- Volltextsuche-Index
CREATE INDEX CONCURRENTLY idx_documents_fulltext
ON documents USING gin(to_tsvector('german', extracted_text));

-- Query-Performance analysieren
EXPLAIN ANALYZE SELECT * FROM documents WHERE status = 'completed' LIMIT 100;
```

### Redis-Optimierung

```bash
# Memory-Policy setzen
docker exec ablage-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Speicher-Info
docker exec ablage-redis redis-cli INFO memory

# Langsame Befehle
docker exec ablage-redis redis-cli SLOWLOG GET 10
```

### Celery-Optimierung

```yaml
# docker-compose.yml
worker:
  command: >
    celery -A app.workers.celery_app worker
    --loglevel=info
    --concurrency=2          # Parallele Tasks
    --prefetch-multiplier=1  # Speicher sparen
    --pool=solo              # GPU-kompatibel
```

### Nginx-Caching

```nginx
# Statische Dateien cachen
location /static/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

# API-Response-Cache (optional)
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m;

location /api/v1/documents {
    proxy_cache api_cache;
    proxy_cache_valid 200 1m;
    proxy_cache_bypass $http_cache_control;
}
```

---

## API-Referenz für Administratoren

### System-Endpunkte

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| GET | `/api/v1/health` | System-Gesundheit |
| GET | `/api/v1/metrics` | Prometheus-Metriken |
| GET | `/api/v1/admin/system/status` | Detaillierter System-Status |
| POST | `/api/v1/admin/maintenance/enable` | Wartungsmodus aktivieren |
| DELETE | `/api/v1/admin/maintenance/enable` | Wartungsmodus deaktivieren |

### Backup-Endpunkte

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| GET | `/api/v1/backup/status` | Backup-Status |
| GET | `/api/v1/backup/list` | Backup-Liste |
| POST | `/api/v1/backup/full` | Vollständiges Backup |
| POST | `/api/v1/backup/postgres` | Nur PostgreSQL |
| POST | `/api/v1/backup/retention` | Alte Backups löschen |

### OCR-Training-Endpunkte

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| GET | `/api/v1/training/stats/overview` | Trainings-Statistiken |
| POST | `/api/v1/training/benchmarks/run` | Benchmark starten |
| GET | `/api/v1/training/benchmarks/compare` | Backend-Vergleich |

---

## Support und Ressourcen

### Dokumentation

- **Benutzerhandbuch:** `docs/USER_GUIDE.md`
- **API-Dokumentation:** http://localhost:8000/docs
- **Architektur:** `ARCHITECTURE.md`
- **Runbooks:** `.claude/Docs/Operations/Runbooks/`

### Kontakt

- **IT-Support:** support@ihre-firma.de
- **Hotline:** +49 123 456789
- **Bereitschaft:** oncall@ihre-firma.de

---

*Letzte Aktualisierung: Januar 2025*
