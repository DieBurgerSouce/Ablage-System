# System Health Check Command

Führt umfassende Systemprüfung durch.

**Anweisungen:**

1. **GPU-Status prüfen:**
```bash
nvidia-smi
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

2. **Docker-Services prüfen:**
```bash
docker-compose ps
```

3. **API-Gesundheit prüfen:**
```bash
curl -s http://localhost:8000/health | python -m json.tool
```

4. **Datenbank-Verbindung prüfen:**
```bash
docker-compose exec postgres pg_isready -U postgres
```

5. **Redis-Verbindung prüfen:**
```bash
docker-compose exec redis redis-cli ping
```

6. **Celery-Worker prüfen:**
```bash
celery -A app.workers.celery_app inspect active
```

7. **MinIO-Status prüfen:**
```bash
curl -s http://localhost:9000/minio/health/live
```

**Ausgabe-Format:**
```
=== Ablage-System Gesundheitscheck ===

[GPU]       RTX 4080    ✓ 12.3GB frei / 16GB
[API]       FastAPI     ✓ läuft auf :8000
[DB]        PostgreSQL  ✓ verbunden
[Cache]     Redis       ✓ verbunden
[Queue]     Celery      ✓ 1 Worker aktiv
[Storage]   MinIO       ✓ erreichbar
[OCR]       DeepSeek    ✓ bereit
            GOT-OCR     ✓ bereit
            Surya       ✓ bereit (CPU)

Gesamtstatus: ✓ ALLE SYSTEME OPERABEL
```
