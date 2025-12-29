---
name: ocr-debug
description: Diagnostiziere OCR-Probleme im Ablage-System. Nutze diesen Skill bei GPU-Fehlern, schlechter Texterkennung, Umlaut-Problemen, VRAM-Ueberlaeufen oder Performance-Issues. Unterstuetzt DeepSeek, GOT-OCR und Surya Backends.
---

# OCR Debugging (Ablage-System)

Diagnostiziere und behebe OCR-Probleme systematisch.

## Quick Check

```bash
# GPU Status
nvidia-smi

# VRAM Nutzung (sollte unter 85% = 13.6GB bleiben)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# CUDA im Container
docker-compose exec worker python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}')"
```

## OCR Backends

| Backend | VRAM | GPU | Staerken |
|---------|------|-----|----------|
| DeepSeek-Janus-Pro | 12GB | Ja | Beste Umlaut-Genauigkeit, Fraktur |
| GOT-OCR 2.0 | 10GB | Nein* | Tabellen, Formeln, schnell |
| Surya + Docling | 0GB | Nein | CPU-Fallback, Layout-Analyse |
| Surya GPU | 4GB | Ja | Schnelle GPU-Variante |

## Haeufige Probleme

### 1. GPU OOM (Out of Memory)

**Symptome**: CUDA out of memory, Worker crashed

```bash
# VRAM freigeben
docker-compose exec worker python -c "import torch; torch.cuda.empty_cache()"

# Worker neustarten
docker-compose restart worker

# Batch-Groesse reduzieren (in app/core/config.py)
OCR_BATCH_SIZE=8  # Standard: 16
```

### 2. Schlechte Umlaut-Erkennung

**Symptome**: ae statt ä, ss statt ß

```python
# Backend wechseln zu DeepSeek (beste Umlaut-Genauigkeit)
# In app/services/ocr/orchestrator.py

def select_backend(self, document):
    if document.language == "de":
        return "deepseek"  # Immer DeepSeek fuer Deutsch
```

**Post-Processing aktivieren**:
```python
from app.utils.german_text import normalize_german_text
text = normalize_german_text(ocr_result)
```

### 3. Fraktur-Schrift nicht erkannt

**Loesung**: DeepSeek mit Fraktur-Flag

```python
deepseek_config = {
    "language": "de",
    "detect_fraktur": True,
    "umlauts_priority": True
}
```

### 4. Langsame Verarbeitung

**Diagnose**:
```bash
# GPU-Auslastung pruefen
watch -n 1 nvidia-smi

# Worker-Logs
docker-compose logs -f worker | grep -i "processing\|time\|duration"
```

**Optimierungen**:
- Batch-Verarbeitung aktivieren
- Vorverarbeitung optimieren (Resize, Denoise)
- GOT-OCR fuer einfache Dokumente (schneller)

### 5. Worker startet nicht

```bash
# Logs pruefen
docker-compose logs worker | tail -50

# GPU-Treiber pruefen
nvidia-smi

# Container neu bauen
docker-compose build --no-cache worker
docker-compose up -d worker
```

## Backend-Auswahl Logic

```python
# app/services/ocr/orchestrator.py

def select_backend(self, document):
    # Komplexe Layouts -> DeepSeek
    if document.has_tables or document.has_images:
        return "deepseek"

    # Deutsche Dokumente -> DeepSeek (Umlaute!)
    if document.language == "de":
        return "deepseek"

    # Schnelle Verarbeitung gewuenscht -> GOT-OCR
    if document.priority == "fast":
        return "got_ocr"

    # GPU nicht verfuegbar -> Surya CPU
    if not torch.cuda.is_available():
        return "surya"

    # Default
    return "deepseek"
```

## Metriken pruefen

```bash
# Prometheus Metriken
curl http://localhost:8000/metrics | grep ocr

# Relevante Metriken:
# - ocr_requests_total
# - ocr_processing_duration_seconds
# - ocr_errors_total
# - gpu_memory_usage_bytes
```

## Grafana Dashboards

- **OCR Performance**: http://localhost:3002/d/ocr-performance
- **GPU Monitoring**: http://localhost:3002/d/gpu-monitoring

## Debug-Logging aktivieren

```python
# In app/core/config.py
LOG_LEVEL = "DEBUG"

# Oder via Environment
docker-compose exec worker env LOG_LEVEL=DEBUG celery ...
```

## Test-Dokumente

```bash
# OCR Benchmark mit Test-Dokumenten
docker-compose exec backend python -m pytest tests/ocr/ -v

# Einzelnes Dokument testen
docker-compose exec backend python -c "
from app.services.ocr.orchestrator import OCROrchestrator
ocr = OCROrchestrator()
result = ocr.process_file('/path/to/test.pdf')
print(result.text[:500])
"
```
