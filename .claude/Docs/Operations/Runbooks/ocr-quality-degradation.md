# OCR Quality Degradation Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 1 Stunde | RPO: Dokumente können erneut verarbeitet werden

## Alert

```
OCRQualityCERWarning - CER > 5%
OCRQualityCERCritical - CER > 10%
OCRQualityWERCritical - WER > 15%
UmlautAccuracyDegraded - < 98%
```

## Symptome

- Character Error Rate (CER) über 5%
- Word Error Rate (WER) über 15%
- Umlaut-Genauigkeit unter 98%
- Benutzer melden falsch erkannte Texte
- Hohe Korrekturrate bei manueller Überprüfung

---

## Sofortmaßnahmen (< 10 Minuten)

### 1. Aktuelle Qualitätsmetriken prüfen

```bash
# OCR-Qualitätsmetriken abrufen
curl -s http://localhost:8000/api/v1/metrics | grep -E "ocr_quality|cer|wer|umlaut"

# Dashboard-Link
echo "Grafana: http://localhost:3002/d/ablage-ocr-pipeline"
```

### 2. Backend-Verteilung analysieren

```bash
# Welches Backend liefert schlechte Ergebnisse?
docker exec ablage-backend python -c "
from app.services.ocr_metrics_service import OCRMetricsService
metrics = OCRMetricsService()
for backend in ['deepseek', 'got_ocr', 'surya', 'surya_gpu']:
    stats = metrics.get_backend_stats(backend, hours=1)
    print(f'{backend}: CER={stats.cer:.2%}, WER={stats.wer:.2%}, Umlaut={stats.umlaut_accuracy:.2%}')
"
```

### 3. Letzte Dokumente mit Problemen identifizieren

```bash
# Dokumente mit niedriger Konfidenz (letzte Stunde)
docker exec ablage-backend python -c "
from app.db.repositories.document_repository import DocumentRepository
from app.db.session import get_db
from datetime import datetime, timedelta

async def check():
    async with get_db() as db:
        repo = DocumentRepository(db)
        docs = await repo.get_low_confidence_documents(
            min_confidence=0.7,
            since=datetime.utcnow() - timedelta(hours=1)
        )
        for doc in docs[:10]:
            print(f'{doc.id}: {doc.filename} - Conf: {doc.ocr_confidence:.2f}, Backend: {doc.ocr_backend_used}')

import asyncio
asyncio.run(check())
"
```

---

## Diagnose (10-30 Minuten)

### 4. Dokumenttypen analysieren

```bash
# Welche Dokumenttypen haben Probleme?
docker exec ablage-backend python -c "
from app.services.analytics_service import AnalyticsService

svc = AnalyticsService()
by_type = svc.get_quality_by_document_type(hours=24)
for doc_type, metrics in sorted(by_type.items(), key=lambda x: x[1]['cer'], reverse=True):
    print(f'{doc_type}: CER={metrics[\"cer\"]:.2%}, Count={metrics[\"count\"]}')
"
```

### 5. Bildqualität prüfen

```bash
# Dokumente mit niedriger DPI oder schlechter Qualität
docker exec ablage-backend python -c "
from app.services.preprocessing_service import PreprocessingService

svc = PreprocessingService()
issues = svc.get_quality_issues(hours=1)
for issue in issues[:5]:
    print(f'{issue.document_id}: {issue.issue_type} - {issue.description}')
"
```

### 6. GPU-Status prüfen

```bash
# GPU-Temperatur und Throttling
nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.sm --format=csv

# Falls Temperatur > 80°C: Throttling möglich
```

---

## Lösung

### Option A: Backend wechseln

```bash
# Temporär auf zuverlässigeres Backend wechseln
docker exec ablage-backend python -c "
from app.core.config import update_runtime_setting
update_runtime_setting('OCR_PREFERRED_BACKEND', 'deepseek')
update_runtime_setting('OCR_FALLBACK_BACKENDS', ['got_ocr', 'surya'])
"

# Oder via API
curl -X POST http://localhost:8000/api/v1/admin/settings \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ocr_preferred_backend": "deepseek"}'
```

### Option B: Preprocessing optimieren

```bash
# Bildverbesserung aktivieren
docker exec ablage-backend python -c "
from app.core.config import update_runtime_setting
update_runtime_setting('OCR_PREPROCESSING_ENABLED', True)
update_runtime_setting('OCR_DESKEW_ENABLED', True)
update_runtime_setting('OCR_DENOISE_ENABLED', True)
update_runtime_setting('OCR_CONTRAST_ENHANCEMENT', True)
"
```

### Option C: Model-Cache leeren

```bash
# Model-Cache bereinigen (kann bei korrupten Weights helfen)
docker exec ablage-worker python -c "
from app.agents.ocr.model_manager import ModelManager
mm = ModelManager()
mm.clear_cache()
mm.preload_models(['deepseek', 'surya_gpu'])
"

# Worker neustarten
docker-compose restart worker
```

### Option D: Betroffene Dokumente erneut verarbeiten

```bash
# Dokumente mit niedriger Qualität zur erneuten Verarbeitung markieren
docker exec ablage-backend python -c "
from app.services.reprocessing_service import ReprocessingService
from datetime import datetime, timedelta

svc = ReprocessingService()
count = svc.queue_low_quality_documents(
    min_confidence=0.7,
    since=datetime.utcnow() - timedelta(hours=24),
    backend='deepseek'  # Mit besserem Backend
)
print(f'{count} Dokumente zur erneuten Verarbeitung eingereiht')
"
```

---

## Umlaut-spezifische Probleme

### Umlaut-Korrektur aktivieren

```bash
# German Correction Agent aktivieren
docker exec ablage-backend python -c "
from app.core.config import update_runtime_setting
update_runtime_setting('GERMAN_CORRECTION_ENABLED', True)
update_runtime_setting('UMLAUT_RESTORATION_ENABLED', True)
update_runtime_setting('UMLAUT_CONFIDENCE_THRESHOLD', 0.8)
"
```

### Umlaut-Validierung prüfen

```bash
# Umlaut-Statistiken
docker exec ablage-backend python -c "
from app.services.german_validation_service import GermanValidationService

svc = GermanValidationService()
stats = svc.get_umlaut_statistics(hours=24)
print(f'Korrekt: {stats.correct_count}')
print(f'Korrigiert: {stats.corrected_count}')
print(f'Fehlend: {stats.missing_count}')
print(f'Genauigkeit: {stats.accuracy:.2%}')
"
```

---

## Verifikation

```bash
# Qualitätsmetriken nach Fix
curl -s http://localhost:8000/api/v1/training/stats/overview | jq

# Test mit bekanntem Dokument
curl -X POST http://localhost:8000/api/v1/ocr/test \
  -F "file=@tests/fixtures/german_docs/invoices/invoice_001.png" \
  | jq '.confidence, .cer, .umlaut_accuracy'
```

---

## Benchmark durchführen

```bash
# Vollständiger OCR-Benchmark
docker exec ablage-backend python -c "
from app.services.benchmark_runner_service import BenchmarkRunnerService
import asyncio

async def run():
    svc = BenchmarkRunnerService()
    results = await svc.run_full_benchmark(
        categories=['invoices', 'contracts'],
        backends=['deepseek', 'got_ocr', 'surya_gpu']
    )
    for backend, metrics in results.items():
        print(f'{backend}: CER={metrics.cer:.2%}, WER={metrics.wer:.2%}, Umlaut={metrics.umlaut_accuracy:.2%}')

asyncio.run(run())
"
```

---

## Metriken & Dashboards

- **Grafana Dashboard**: "OCR Pipeline Monitoring"
- **Prometheus Queries**:
  ```promql
  # CER nach Backend
  ocr_quality_cer{backend="deepseek"}

  # Umlaut-Genauigkeit
  ocr_umlaut_accuracy

  # Backend-Vergleich
  histogram_quantile(0.95, ocr_processing_duration_seconds_bucket)
  ```

---

## Eskalation

| CER | Aktion |
|-----|--------|
| 5-8% | On-Call: Backend wechseln |
| 8-15% | ML-Team: Model-Analyse |
| 15%+ | Eskalation: Stopp Verarbeitung |

---

## Verwandte Runbooks

- [GPU OOM Recovery](gpu-oom-recovery.md)
- [Celery Worker Recovery](celery-worker-restart.md)
- [OCR Benchmark](../../../commands/ocr-benchmark.md)
