# GPU OOM Recovery Runbook

**Version:** 1.0
**Letzte Aktualisierung:** 2025-12-18
**Hardware:** NVIDIA RTX 4080 (16GB VRAM)
**Verantwortlich:** ML/OCR Team

---

## 1. Übersicht

Dieses Runbook beschreibt die Diagnose und Behebung von GPU Out-of-Memory (OOM) Fehlern im Ablage-System OCR.

### VRAM-Anforderungen pro Backend

| Backend | VRAM | Max Batch | Fallback |
|---------|------|-----------|----------|
| DeepSeek-Janus-Pro | 12GB | 2 Bilder | GOT-OCR |
| GOT-OCR 2.0 | 10GB | 4 Bilder | Surya |
| Surya GPU | 8GB | 8 Bilder | Surya CPU |
| Donut | 8GB | 4 Bilder | Surya CPU |

### Schwellenwerte

- **Normal:** < 80% VRAM (< 12.8GB)
- **Warnung:** 80-85% VRAM (12.8-13.6GB)
- **Kritisch:** > 85% VRAM (> 13.6GB)

---

## 2. Diagnose

### 2.1 Sofort-Check

```bash
# GPU-Status prüfen
nvidia-smi

# Detaillierte GPU-Nutzung
nvidia-smi --query-gpu=memory.used,memory.free,memory.total,utilization.gpu,temperature.gpu --format=csv

# GPU-Prozesse auflisten
nvidia-smi pmon -s um -d 1

# Python GPU-Memory
python3 -c "
import torch
if torch.cuda.is_available():
    print(f'VRAM Used: {torch.cuda.memory_allocated()/1024**3:.2f} GB')
    print(f'VRAM Cached: {torch.cuda.memory_reserved()/1024**3:.2f} GB')
    print(f'Max VRAM: {torch.cuda.max_memory_allocated()/1024**3:.2f} GB')
"
```

### 2.2 Celery Worker prüfen

```bash
# Worker-Status
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Aktive OCR-Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect reserved

# GPU Lock Status (Redis)
docker exec ablage-redis redis-cli GET "gpu:lock:0"
docker exec ablage-redis redis-cli TTL "gpu:lock:0"
```

### 2.3 Logs analysieren

```bash
# OOM-Fehler in Worker-Logs
docker-compose logs worker | grep -i "out of memory\|OOM\|cuda error"

# Backend-Wechsel-Events
docker-compose logs worker | grep -i "fallback\|switching backend"

# GPU Recovery Events
docker-compose logs worker | grep -i "gpu_recovery\|memory_cleared"
```

---

## 3. Sofortmaßnahmen

### 3.1 GPU-Speicher freigeben (Soft)

```bash
# Worker graceful restart
docker-compose exec worker celery -A app.workers.celery_app control shutdown

# Warte 30 Sekunden für Task-Completion
sleep 30

# Worker neu starten
docker-compose up -d worker
```

### 3.2 GPU-Speicher freigeben (Hart)

```bash
# WARNUNG: Laufende Tasks werden abgebrochen!

# Worker sofort stoppen
docker-compose stop worker

# GPU-Speicher komplett freigeben
nvidia-smi --gpu-reset

# Worker neu starten
docker-compose up -d worker
```

### 3.3 Einzelnen OCR-Prozess killen

```bash
# Prozesse mit GPU-Nutzung finden
nvidia-smi pmon -s um -c 1

# Spezifischen Prozess killen (nach PID)
docker exec ablage-worker kill -9 <PID>

# Oder: Alle Python-Prozesse im Worker
docker exec ablage-worker pkill -f "python.*ocr"
```

### 3.4 GPU Lock manuell freigeben

```bash
# Falls GPU-Lock hängt
docker exec ablage-redis redis-cli DEL "gpu:lock:0"

# Lock-Status prüfen
docker exec ablage-redis redis-cli KEYS "gpu:*"
```

---

## 4. Präventive Konfiguration

### 4.1 VRAM-Limits konfigurieren

```python
# app/core/config.py - Empfohlene Einstellungen

GPU_MEMORY_FRACTION = 0.85  # Max 85% VRAM nutzen
GPU_LOCK_TIMEOUT = 180      # 3 Minuten Lock-Timeout
MAX_BATCH_SIZE = 4          # Max Bilder pro Batch
```

### 4.2 Worker-Konfiguration anpassen

```yaml
# docker-compose.yml - Worker-Service
worker:
  environment:
    - PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
    - CUDA_VISIBLE_DEVICES=0
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']
            capabilities: [gpu]
```

### 4.3 Automatische Recovery aktivieren

```python
# Celery Task mit OOM-Handling
@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(torch.cuda.OutOfMemoryError,),
    retry_backoff=True,
    retry_backoff_max=600
)
def process_ocr_task(self, document_id: str):
    try:
        return process_document(document_id)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        raise self.retry(countdown=60)
```

---

## 5. Fallback-Strategien

### 5.1 Backend-Fallback-Chain

```
DeepSeek (OOM) → GOT-OCR → Surya GPU → Surya CPU
```

### 5.2 Manueller Backend-Wechsel

```bash
# API-Endpoint für Backend-Wechsel
curl -X POST "http://localhost:8000/api/v1/ocr/backend/switch" \
  -H "Content-Type: application/json" \
  -d '{"backend": "surya_cpu", "reason": "gpu_oom"}'

# Aktuelles Backend prüfen
curl "http://localhost:8000/api/v1/ocr/backend/status" | jq .
```

### 5.3 Batch-Size reduzieren

```bash
# Runtime-Anpassung via API
curl -X POST "http://localhost:8000/api/v1/ocr/config" \
  -H "Content-Type: application/json" \
  -d '{"max_batch_size": 2}'
```

---

## 6. Monitoring & Alerts

### 6.1 Prometheus-Metriken

```promql
# GPU Memory Usage
nvidia_gpu_memory_used_bytes{gpu="0"} / nvidia_gpu_memory_total_bytes{gpu="0"}

# OOM Events Counter
increase(ablage_gpu_oom_total[1h])

# Alert Rule
- alert: GPUMemoryHigh
  expr: nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes > 0.85
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "GPU Memory über 85%"
```

### 6.2 Grafana Dashboard

- Panel: GPU Memory Usage (Gauge)
- Panel: OOM Events (Counter)
- Panel: Backend Fallback Events (Counter)
- Panel: OCR Processing Time by Backend (Histogram)

---

## 7. Häufige Ursachen

| Ursache | Symptom | Lösung |
|---------|---------|--------|
| Zu große Batch-Size | OOM bei Batch-Start | Batch-Size reduzieren |
| Memory Leak | VRAM steigt kontinuierlich | Worker regelmäßig neu starten |
| Concurrent GPU Access | Sporadische OOMs | GPU-Locking verbessern |
| Große Dokumente | OOM bei einzelnen Docs | Seitenweise verarbeiten |
| Model nicht entladen | VRAM bleibt hoch | Model-Caching prüfen |

---

## 8. Post-OOM Checkliste

- [ ] GPU-Speicher zurück unter 80%
- [ ] Worker läuft wieder
- [ ] GPU-Lock freigegeben
- [ ] Celery Queue nicht blockiert
- [ ] Keine fehlgeschlagenen Tasks in DLQ
- [ ] Monitoring zeigt normale Werte
- [ ] Betroffene Dokumente neu in Queue

---

## 9. Eskalation

| Situation | Aktion |
|-----------|--------|
| OOM alle 5 Minuten | Team informieren, Batch-Size halbieren |
| Worker startet nicht mehr | On-Call eskalieren |
| GPU nicht erkannt | Hardware-Team kontaktieren |
| Alle Backends fallen aus | SEV-1 Incident eröffnen |

---

## 10. Nützliche Befehle

```bash
# GPU komplett zurücksetzen
sudo nvidia-smi --gpu-reset

# CUDA Cache leeren
rm -rf ~/.cache/torch/

# Model Cache leeren
rm -rf ~/.cache/huggingface/

# Worker mit GPU-Debug starten
CUDA_LAUNCH_BLOCKING=1 docker-compose up worker
```
