---
name: docker-dev
description: Docker-Entwicklung fuer das Ablage-System. Nutze diesen Skill wenn du Container bauen, Services starten, Logs pruefen oder GPU-Container handhaben musst. Alle Entwicklung erfolgt ausschliesslich via Docker!
---

# Docker Development (Ablage-System)

**WICHTIG**: Keine lokalen Dev-Server! Alle Aenderungen via Docker testen.

## Quick Reference

```bash
# Alles starten
docker-compose up -d

# Status pruefen
docker-compose ps

# Logs folgen
docker-compose logs -f [service]
```

## Services

| Service | Port | Beschreibung |
|---------|------|--------------|
| frontend | 80 | Nginx + React |
| backend | 8000 | FastAPI |
| worker | - | Celery (GPU) |
| postgres | 5433 | PostgreSQL 16 |
| redis | 6380 | Cache + Queue |
| minio | 9000/9001 | Object Storage |
| grafana | 3002 | Monitoring |
| prometheus | 9090 | Metriken |

## Build Commands

```bash
# Frontend neu bauen (nach React-Aenderungen)
docker-compose build frontend && docker-compose up -d frontend

# Backend neu bauen (nach Python-Aenderungen)
docker-compose build backend && docker-compose up -d backend

# Worker neu bauen (nach OCR-Aenderungen)
docker-compose build worker && docker-compose up -d worker

# Alles neu bauen
docker-compose build && docker-compose up -d
```

## GPU Container

```bash
# GPU-Status im Container pruefen
docker-compose exec worker nvidia-smi

# CUDA-Verfuegbarkeit testen
docker-compose exec worker python -c "import torch; print(torch.cuda.is_available())"

# Worker mit GPU-Logs starten
docker-compose logs -f worker
```

## Debugging

### Container laeuft nicht
```bash
# Exit-Logs pruefen
docker-compose logs --tail=50 [service]

# Container-Status
docker-compose ps -a

# Neustart erzwingen
docker-compose down && docker-compose up -d
```

### Speicherplatz voll
```bash
# Aufraumen
docker system prune -a --volumes

# Images auflisten
docker images

# Dangling Images loeschen
docker image prune
```

### Port-Konflikte
```bash
# Wer nutzt Port 8000?
netstat -ano | findstr :8000

# Docker-Ports pruefen
docker-compose ps
```

## Tests in Docker

```bash
# Unit Tests
docker-compose exec backend pytest tests/unit/ -v

# Integration Tests
docker-compose exec backend pytest tests/integration/ -v

# Mit Coverage
docker-compose exec backend pytest --cov=app --cov-report=html
```

## Datenbank

```bash
# PostgreSQL Shell
docker-compose exec postgres psql -U postgres -d ablage

# Migrationen ausfuehren
docker-compose exec backend alembic upgrade head

# Neue Migration erstellen
docker-compose exec backend alembic revision --autogenerate -m "description"
```

## Celery

```bash
# Worker-Status
docker-compose exec worker celery -A app.workers.celery_app inspect active

# Queue-Laenge
docker-compose exec worker celery -A app.workers.celery_app inspect reserved

# Flower (Task-Monitoring)
# http://localhost:5555
```

## Haeufige Probleme

### "GPU nicht erkannt"
```bash
# Docker GPU Support pruefen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# docker-compose.yml pruefen: deploy.resources.reservations.devices
```

### "Module not found"
```bash
# Requirements aktualisiert?
docker-compose build --no-cache backend
```

### "Database connection refused"
```bash
# Postgres laeuft?
docker-compose ps postgres

# Connection-String pruefen
docker-compose exec backend env | grep DATABASE
```

### "Redis connection error"
```bash
# Redis laeuft?
docker-compose ps redis

# Redis ping
docker-compose exec redis redis-cli ping
```
