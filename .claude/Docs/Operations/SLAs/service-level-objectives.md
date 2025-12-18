# Service Level Objectives (SLOs)

**Version:** 1.0
**Letzte Aktualisierung:** 2025-12-18
**Gültig ab:** Q1 2025

---

## 1. Übersicht

Dieses Dokument definiert die Service Level Objectives (SLOs) für das Ablage-System OCR. SLOs sind messbare Ziele, die die Qualität des Services definieren.

---

## 2. Availability SLOs

### 2.1 System-Verfügbarkeit

| Service | SLO | Messmethode | Ausnahmen |
|---------|-----|-------------|-----------|
| **API Gateway** | 99.9% (8.76h/Jahr Downtime) | Health Check alle 30s | Geplante Wartung |
| **OCR Processing** | 99.5% (43.8h/Jahr Downtime) | Task Success Rate | GPU-Wartung |
| **Database** | 99.95% (4.38h/Jahr Downtime) | Connection Success | Backup-Window |
| **Storage (MinIO)** | 99.9% (8.76h/Jahr Downtime) | Object Availability | - |

### 2.2 Berechnung

```
Availability = (Total Time - Downtime) / Total Time × 100%

Beispiel (monatlich):
- 30 Tage = 43,200 Minuten
- 99.9% = max 43.2 Minuten Downtime
- 99.5% = max 216 Minuten Downtime
```

---

## 3. Latency SLOs

### 3.1 API Response Times (p95)

| Endpoint-Kategorie | SLO (p95) | SLO (p99) | Max |
|--------------------|-----------|-----------|-----|
| **Health Check** | < 50ms | < 100ms | 200ms |
| **Authentication** | < 200ms | < 500ms | 1s |
| **Document Upload** | < 500ms | < 1s | 5s |
| **Document Retrieval** | < 100ms | < 300ms | 1s |
| **Search Query** | < 500ms | < 1s | 3s |
| **List Operations** | < 300ms | < 500ms | 2s |

### 3.2 OCR Processing Times (p95)

| Dokument-Typ | SLO (p95) | SLO (p99) | Backend |
|--------------|-----------|-----------|---------|
| **Einzelseite (A4, 300 DPI)** | < 2s | < 5s | DeepSeek |
| **Mehrseitig (bis 10 Seiten)** | < 500ms/Seite | < 1s/Seite | DeepSeek |
| **Batch (32 Dokumente)** | < 10s | < 30s | DeepSeek |
| **CPU Fallback** | < 10s/Seite | < 20s/Seite | Surya |

### 3.3 Messung

```python
# Prometheus Histogramm-Buckets für Latenz
LATENCY_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

# PromQL für p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

---

## 4. Throughput SLOs

### 4.1 Request Throughput

| Metrik | SLO | Peak-Load |
|--------|-----|-----------|
| **API Requests/Sekunde** | 100 RPS sustained | 500 RPS burst |
| **Concurrent Users** | 100 gleichzeitig | 250 peak |
| **Document Uploads/Stunde** | 500 | 1000 |
| **OCR Jobs/Stunde** | 300 (GPU) | 100 (CPU fallback) |

### 4.2 Batch Processing

| Metrik | SLO |
|--------|-----|
| **Batch Job Start** | < 30s nach Submit |
| **Queue Backlog** | < 100 Jobs |
| **DLQ Size** | < 10 Jobs |

---

## 5. Quality SLOs

### 5.1 OCR Accuracy

| Dokument-Typ | SLO (CER) | SLO (WER) | Umlaut-Genauigkeit |
|--------------|-----------|-----------|-------------------|
| **Moderne Druckschrift** | < 2% | < 5% | 99.5% |
| **Handschrift** | < 10% | < 15% | 98% |
| **Fraktur** | < 5% | < 10% | 99% |
| **Tabellen** | < 3% | < 7% | 99% |

### 5.2 Data Integrity

| Metrik | SLO |
|--------|-----|
| **Document Loss Rate** | 0% (Zero Data Loss) |
| **Backup Success Rate** | 99.9% |
| **Restore Success Rate** | 100% |

---

## 6. Error Budget

### 6.1 Definition

```
Error Budget = 1 - SLO

Beispiel für 99.9% Availability:
Error Budget = 0.1% = 43.2 Minuten/Monat
```

### 6.2 Error Budget Policy

| Budget-Status | Maßnahme |
|---------------|----------|
| **> 50% verbleibend** | Normal: Features & Fixes |
| **25-50% verbleibend** | Vorsicht: Priorisiere Stabilität |
| **< 25% verbleibend** | Freeze: Nur kritische Fixes |
| **0% (aufgebraucht)** | Incident: Keine Deployments bis Reset |

### 6.3 Budget-Tracking

```promql
# Verbleibendes Error Budget (%)
(1 - (
  sum(rate(http_requests_total{status=~"5.."}[30d])) /
  sum(rate(http_requests_total[30d]))
)) / 0.001 * 100
```

---

## 7. Recovery SLOs (RTO/RPO)

### 7.1 Recovery Time Objective (RTO)

| Szenario | RTO |
|----------|-----|
| **API Neustart** | < 5 Minuten |
| **Worker Failover** | < 2 Minuten |
| **Database Failover** | < 30 Sekunden (mit Patroni) |
| **Vollständiger Restore** | < 4 Stunden |
| **Region Failover** | < 1 Stunde |

### 7.2 Recovery Point Objective (RPO)

| Komponente | RPO |
|------------|-----|
| **Transaktionsdaten** | 0 (synchron) |
| **Dokumente** | < 1 Stunde |
| **OCR-Ergebnisse** | < 24 Stunden (regenerierbar) |
| **Konfiguration** | 0 (Git-versioniert) |

---

## 8. SLI-Definitionen

### 8.1 Service Level Indicators

```yaml
# Availability SLI
availability_sli:
  name: "API Availability"
  query: |
    sum(rate(http_requests_total{status!~"5.."}[5m])) /
    sum(rate(http_requests_total[5m]))
  good_threshold: 0.999

# Latency SLI
latency_sli:
  name: "API Latency p95"
  query: |
    histogram_quantile(0.95,
      sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
    )
  good_threshold: 0.5  # 500ms

# Error Rate SLI
error_sli:
  name: "Error Rate"
  query: |
    sum(rate(http_requests_total{status=~"5.."}[5m])) /
    sum(rate(http_requests_total[5m]))
  good_threshold: 0.001  # 0.1%
```

---

## 9. Reporting

### 9.1 SLO Dashboard

- **URL:** http://localhost:3002/d/slo-overview
- **Update-Frequenz:** Real-time
- **Retention:** 90 Tage

### 9.2 Monatlicher SLO Report

| Abschnitt | Inhalt |
|-----------|--------|
| Executive Summary | SLO-Status auf einen Blick |
| Availability | Uptime pro Service |
| Latency | p50, p95, p99 Trends |
| Error Budget | Verbrauch vs. Verbleibend |
| Incidents | Auswirkung auf SLOs |
| Action Items | Verbesserungsmaßnahmen |

---

## 10. Änderungshistorie

| Version | Datum | Änderung | Autor |
|---------|-------|----------|-------|
| 1.0 | 2025-12-18 | Initiale Version | Claude |
