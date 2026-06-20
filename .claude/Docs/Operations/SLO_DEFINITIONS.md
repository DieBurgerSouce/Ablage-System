# Service Level Objectives (SLO) — Ablage-System

> **Version:** 1.0 · **Gültig ab:** 2026-06-20 · **Status:** initial, gegen echten Code/Metriken verifiziert (OPEN-54)
> **Kontext:** On-Premises Single-Host (RTX 4080). Ziel-Setting: 1-Kunden-Pilot → kleine Mehrkunden-Basis. Targets sind bewusst konservativ und auf das tatsächliche Deployment skaliert.

SLI = gemessene Größe · SLO = Zielwert · Error-Budget = erlaubter Rest. Metrik-Namen unten sind gegen `app/core/telemetry.py`, `app/core/business_metrics.py` und `app/ml/metrics.py` geprüft. Mit ⚠️ markierte Metriken sind **noch nicht implementiert** (Backlog) — die zugehörigen Alerts dürfen erst nach Implementierung scharfgeschaltet werden.

---

## 1. API-Verfügbarkeit & Latenz

| SLI | SLO-Ziel | Fenster | PromQL (Quelle) |
|-----|----------|---------|-----------------|
| `/health`-Erfolgsrate | 99,9 % | 30 d | `sum(rate(http_requests_total{handler="/health",status=~"2.."}[5m])) / sum(rate(http_requests_total{handler="/health"}[5m]))` |
| API-Latenz p95 | < 50 ms | 5 min | `histogram_quantile(0.95, rate(ablage_api_request_duration_seconds_bucket[5m]))` |
| API-Latenz p99 | < 100 ms | 5 min | `histogram_quantile(0.99, rate(ablage_api_request_duration_seconds_bucket[5m]))` |

**Error-Budget (99,9 %/30 d):** ~43 min Ausfall/Monat. Alert-Schwellen: p95 > 100 ms → Warning, p99 > 200 ms → Critical.

## 2. Dokument-Upload

| SLI | SLO-Ziel | Fenster | PromQL |
|-----|----------|---------|--------|
| Upload-Erfolgsrate | 99,5 % | 30 d | `sum(rate(ablage_documents_uploaded_total{status="success"}[5m])) / sum(rate(ablage_documents_uploaded_total[5m]))` |
| Upload-Latenz p95 | < 500 ms | 5 min | `histogram_quantile(0.95, rate(ablage_document_upload_duration_seconds_bucket[5m]))` ⚠️ |
| Durchsatz | ≥ 500 Dok/h (GPU) | 15 min | `rate(ablage_documents_uploaded_total[15m]) * 3600` |

## 3. OCR-Verarbeitung (GPU)

| SLI | SLO-Ziel | Fenster | PromQL |
|-----|----------|---------|--------|
| OCR-Erfolgsrate | 99,5 % | 30 d | `sum(rate(ablage_ocr_requests_total{status="success"}[5m])) / sum(rate(ablage_ocr_requests_total[5m]))` |
| OCR-Latenz p95 (GPU) | < 2 s | 5 min | `histogram_quantile(0.95, rate(ablage_ocr_request_duration_seconds_bucket{backend=~"deepseek|got_ocr"}[5m]))` |
| OCR-Latenz p95 (CPU-Fallback) | < 10 s | 5 min | `histogram_quantile(0.95, rate(ablage_ocr_request_duration_seconds_bucket{backend="surya"}[5m]))` |
| OCR-Konfidenz Median | ≥ 0,80 | 15 min | `histogram_quantile(0.50, rate(ablage_ocr_confidence_score_bucket[5m]))` |
| Umlaut-Genauigkeit p01 | ≥ 0,99 | 1 h | `histogram_quantile(0.01, rate(ocr_umlaut_accuracy_bucket[5m]))` |
| CER p95 | < 0,05 | 1 h | `histogram_quantile(0.95, rate(ocr_character_error_rate_bucket[5m]))` |
| WER p95 | < 0,10 | 1 h | `histogram_quantile(0.95, rate(ocr_word_error_rate_bucket[5m]))` |

> **Wichtig (OPEN-53):** Die Alerts in `business-alerts.yml` referenzieren `ablage_ocr_cer_estimate_avg` / `ablage_ocr_wer_estimate_avg` — diese Metriken existieren **nicht**. Echt vorhanden sind die Histogramme `ocr_character_error_rate` / `ocr_word_error_rate` / `ocr_umlaut_accuracy` (`app/ml/metrics.py`). Alerts entsprechend auf `histogram_quantile(...)` umstellen.

## 4. Pipeline End-to-End (Upload → OCR → Klassifizierung)

| SLI | SLO-Ziel | Fenster | PromQL |
|-----|----------|---------|--------|
| Pipeline-Completion-Rate | 99 % | 30 d | `sum(rate(ablage_document_status_transitions_total{to_status="classified"}[5m])) / sum(rate(ablage_documents_uploaded_total[5m]))` |
| Pipeline-Latenz p50 | < 10 s | 5 min | `histogram_quantile(0.50, rate(ablage_document_pipeline_duration_seconds_bucket[5m]))` ⚠️ |
| Backpressure | normal (0) | Echtzeit | `ablage_backpressure_status` (`business_metrics.py`) |

## 5. GPU-Ressourcen

| SLI | SLO-Ziel | Fenster | PromQL |
|-----|----------|---------|--------|
| VRAM-Auslastung | < 85 % | 5 min | `ablage_gpu_memory_usage_bytes / ablage_gpu_memory_limit_bytes` |
| OOM-Events | < 1/h | 1 h | `rate(ablage_gpu_oom_events_total[1h]) * 3600` |
| GPU-Temperatur | < 75 °C | 5 min | `DCGM_FI_DEV_GPU_TEMP` ⚠️ (**nur mit `--profile gpu`** verfügbar; sonst Fallback auf OOM-Events als Druck-Proxy — OPEN-53) |

## 6. Abhängigkeiten (harte SLO-Voraussetzungen)

| Service | SLO | Metrik |
|---------|-----|--------|
| FastAPI-Backend | 99,9 % | `up{job="ablage-backend"}` |
| PostgreSQL | 99,99 % | `up{job="postgres"}` |
| Redis | 99,9 % | `up{job="redis"}` |
| ≥ 1 OCR-Backend gesund | 100 % | `sum(ablage_ocr_backend_healthy) >= 1` (`app/ml/metrics.py`) |

---

## 7. Error-Budget-Politik (Deployment-Gate)

| Verbrauch des Monatsbudgets | Regel |
|-----------------------------|-------|
| < 75 % | Normales Deployment erlaubt |
| 75–90 % | Nur Bugfixes/Sicherheitspatches |
| > 90 % | Feature-Freeze, nur Rollback/Hotfix |

## 8. Bekannte Lücken (Backlog, ⚠️-Metriken)

1. `ablage_document_upload_duration_seconds` (Upload-Latenz-Histogramm) — implementieren.
2. `ablage_document_pipeline_duration_seconds` (E2E-Latenz) — implementieren.
3. `*_estimate_avg`-Alerts in `business-alerts.yml` auf echte Histogramme umstellen (OPEN-53).
4. GPU-Thermal-Alerts (`ocr-alerts.yml:209-250`) sind ohne `--profile gpu` „no data" → entweder DCGM dauerhaft aktivieren oder als bedingt dokumentieren (OPEN-53).
5. `ablage_slo_error_budget_remaining`-Gauge + Recording-Rules für SLO-Berechnung — implementieren.

## 9. Review-Kadenz

| Frequenz | Aktion |
|----------|--------|
| Wöchentlich | SLI-Trends + Error-Budget-Verbrauch sichten |
| Monatlich | Budget-Reset, SLO-Einhaltung bewerten, Runbooks updaten |
| Quartal | SLO-Ziele gegen Pilot-/Kunden-Realität rekalibrieren |
