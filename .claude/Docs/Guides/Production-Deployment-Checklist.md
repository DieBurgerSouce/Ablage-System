# Production Deployment Checklist

## Quick Reference für Ablage-System Deployments

Diese Checkliste ist für schnelle Referenz bei Produktions-Deployments gedacht.
Für detaillierte Anleitungen siehe: [Deployment-Production.md](./Deployment-Production.md)

---

## Pre-Deployment Checkliste

### 1. Code-Qualität

- [ ] **Tests bestanden**
  ```bash
  pytest --cov=app --cov-report=term -v
  # Coverage mindestens 80%
  ```

- [ ] **Type Checking clean**
  ```bash
  mypy app/ --strict
  # Keine Fehler
  ```

- [ ] **Linting clean**
  ```bash
  ruff check .
  ruff format --check .
  # Keine Verstöße
  ```

- [ ] **Security Scan**
  ```bash
  bandit -r app/
  safety check -r requirements.txt
  # Keine kritischen Findings
  ```

### 2. Datenbank

- [ ] **Migrations aktuell**
  ```bash
  alembic upgrade head --sql > migration_preview.sql
  # SQL prüfen vor Anwendung
  ```

- [ ] **Backup erstellt**
  ```bash
  pg_dump -h localhost -U postgres ablage > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Rollback-Plan vorbereitet**
  ```bash
  # Letzte gute Migration notieren
  alembic current
  # Bei Problemen:
  # alembic downgrade <revision>
  ```

### 3. Konfiguration

- [ ] **Environment Variables gesetzt**
  ```bash
  # .env.production prüfen:
  - [ ] DATABASE_URL
  - [ ] REDIS_URL
  - [ ] MINIO_ENDPOINT
  - [ ] SECRET_KEY (stark, 32+ Zeichen)
  - [ ] JWT_SECRET_KEY
  - [ ] CORS_ORIGINS
  - [ ] GPU_MEMORY_LIMIT_GB=13.6
  ```

- [ ] **Keine Secrets im Code**
  ```bash
  grep -r "password" app/ --include="*.py"
  grep -r "secret" app/ --include="*.py"
  grep -r "api_key" app/ --include="*.py"
  # Nur Referenzen auf env vars erlaubt
  ```

- [ ] **SSL Zertifikate gültig**
  ```bash
  openssl x509 -in /etc/ssl/certs/ablage.crt -noout -dates
  # Nicht innerhalb 30 Tagen ablaufend
  ```

### 4. Infrastructure

- [ ] **Docker Images gebaut**
  ```bash
  docker-compose build --no-cache
  # Alle Services erfolgreich
  ```

- [ ] **GPU Verfügbarkeit**
  ```bash
  nvidia-smi
  # RTX 4080 erkannt, keine Fehler
  docker run --gpus all nvidia/cuda:12.0-base nvidia-smi
  # GPU im Container verfügbar
  ```

- [ ] **Disk Space**
  ```bash
  df -h /
  # Mindestens 50GB frei
  ```

- [ ] **Memory**
  ```bash
  free -h
  # Mindestens 16GB RAM verfügbar
  ```

---

## Deployment-Prozess

### 1. Maintenance Mode aktivieren

```bash
# Load Balancer umleiten
kubectl annotate ingress ablage-ingress nginx.ingress.kubernetes.io/custom-http-errors="503"

# Oder via Flag
curl -X POST http://localhost:8000/api/v1/admin/maintenance/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 2. Backup erstellen

```bash
# Vollständiges Backup
curl -X POST http://localhost:8000/api/v1/backup/full \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Status prüfen
curl http://localhost:8000/api/v1/backup/status
```

### 3. Services stoppen

```bash
# Graceful Shutdown
docker-compose stop worker  # Zuerst Worker
sleep 30  # Jobs abarbeiten lassen
docker-compose stop backend
docker-compose stop
```

### 4. Deployment durchführen

```bash
# Images pullen
docker-compose pull

# Migrations anwenden
docker-compose run --rm backend alembic upgrade head

# Services starten
docker-compose up -d postgres redis minio
sleep 10  # Services hochfahren lassen

docker-compose up -d backend
sleep 5

docker-compose up -d worker
```

### 5. Health Checks

```bash
# Basis-Check
curl http://localhost:8000/api/v1/health
# Erwartet: {"status": "healthy"}

# Detaillierter Check
curl http://localhost:8000/api/v1/health/detailed | jq

# Pipeline-Check
curl http://localhost:8000/api/v1/health/pipeline | jq

# GPU-Check
curl http://localhost:8000/api/v1/health/gpu-memory | jq
```

### 6. Maintenance Mode deaktivieren

```bash
curl -X POST http://localhost:8000/api/v1/admin/maintenance/disable \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 7. Smoke Tests

```bash
# Test-Dokument hochladen
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $USER_TOKEN" \
  -F "file=@test_document.pdf"

# OCR testen
curl -X POST http://localhost:8000/api/v1/ocr/process \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"document_id": "<doc_id>", "backend": "auto"}'
```

---

## Post-Deployment Checkliste

### 1. Monitoring

- [ ] **Grafana Dashboards**
  - [ ] System Overview grün
  - [ ] OCR Pipeline Dashboard aktiv
  - [ ] Keine Alerts

- [ ] **Prometheus Targets**
  ```bash
  curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | .health'
  # Alle "up"
  ```

- [ ] **Logs prüfen**
  ```bash
  docker-compose logs --tail=100 backend | grep -i error
  docker-compose logs --tail=100 worker | grep -i error
  # Keine kritischen Fehler
  ```

### 2. Performance

- [ ] **Response Times**
  ```bash
  # API Latenz
  curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/v1/health
  # < 50ms erwartet
  ```

- [ ] **GPU Memory**
  ```bash
  nvidia-smi --query-gpu=memory.used,memory.total --format=csv
  # < 85% (13.6GB von 16GB)
  ```

### 3. Funktionalität

- [ ] **Login funktioniert**
- [ ] **Dokument-Upload funktioniert**
- [ ] **OCR-Verarbeitung funktioniert**
- [ ] **Export funktioniert**
- [ ] **Admin-Panel erreichbar**

### 4. Kommunikation

- [ ] **Team informiert**
- [ ] **Release Notes erstellt**
- [ ] **Changelog aktualisiert**

---

## Rollback-Prozedur

Bei kritischen Problemen:

### 1. Sofortiger Rollback

```bash
# Zum letzten stabilen Image
docker-compose down
git checkout <last_stable_tag>
docker-compose up -d

# Oder Docker Image Rollback
docker-compose pull --ignore-pull-failures
docker tag ablage-backend:latest ablage-backend:failed
docker pull ablage-backend:previous
docker tag ablage-backend:previous ablage-backend:latest
docker-compose up -d
```

### 2. Datenbank Rollback

```bash
# Migration zurücksetzen
docker-compose run --rm backend alembic downgrade -1

# Oder aus Backup wiederherstellen
psql -h localhost -U postgres ablage < backup_YYYYMMDD_HHMMSS.sql
```

### 3. Post-Rollback

```bash
# Health Checks durchführen
curl http://localhost:8000/api/v1/health/complete | jq

# Logs auf Fehler prüfen
docker-compose logs --tail=200 | grep -i error
```

---

## Notfall-Kontakte

| Rolle | Kontakt | Verfügbarkeit |
|-------|---------|---------------|
| DevOps Lead | [Name] | 24/7 |
| Backend Lead | [Name] | Bürozeiten |
| Security | [Name] | Bei Incidents |

---

## Quick Commands

### Service Status

```bash
# Alle Services
docker-compose ps

# Health
curl -s http://localhost:8000/api/v1/health | jq

# Detailliert
curl -s http://localhost:8000/api/v1/health/complete | jq
```

### Logs

```bash
# Echtzeit
docker-compose logs -f

# Gefiltert
docker-compose logs --tail=100 backend | grep -E "(ERROR|WARNING)"

# Spezifischer Service
docker-compose logs --tail=500 worker
```

### Restart

```bash
# Einzelner Service
docker-compose restart backend

# Alle Services
docker-compose restart

# Mit Neuaufbau
docker-compose up -d --force-recreate
```

### Debug

```bash
# In Container
docker-compose exec backend bash

# Python Shell
docker-compose exec backend python

# DB Query
docker-compose exec postgres psql -U postgres -d ablage
```

---

## Versions-Tracking

| Version | Datum | Deployer | Notizen |
|---------|-------|----------|---------|
| v1.0.0 | YYYY-MM-DD | [Name] | Initial |
| v1.1.0 | YYYY-MM-DD | [Name] | Feature X |

---

## Siehe auch

- [Deployment-Production.md](./Deployment-Production.md) - Detaillierte Anleitung
- [Troubleshooting-Guide.md](./Troubleshooting-Guide.md) - Problemlösung
- [Disaster-Recovery.md](./Disaster-Recovery.md) - DR-Plan
- [Backup-Recovery-Guide.md](./Backup-Recovery-Guide.md) - Backup-Prozeduren
