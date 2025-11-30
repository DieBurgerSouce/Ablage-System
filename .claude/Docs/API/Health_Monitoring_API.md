# Health & Monitoring API Dokumentation

## Übersicht

Das Ablage-System bietet umfassende Health-Check und Monitoring-Endpoints für:
- Systemgesundheit (Datenbank, Redis, MinIO, GPU)
- Circuit Breaker Status für OCR-Backends
- OCR Pipeline Status
- SLO/SLI Metriken
- GPU Memory Guard

## Basis-URL

```
/api/v1/health
```

---

## Endpoints

### 1. Basis Health Check

**GET** `/api/v1/health`

Schneller Health Check für Load Balancer und Kubernetes Probes.

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2024-11-30T10:30:00Z",
    "version": "1.0.0"
}
```

**Status Codes:**
- `200 OK`: System gesund
- `503 Service Unavailable`: System nicht gesund

---

### 2. Detaillierter Health Check

**GET** `/api/v1/health/detailed`

Umfassende Prüfung aller Systemkomponenten.

**Response:**
```json
{
    "status": "healthy",
    "checks": {
        "database": {
            "status": "healthy",
            "latency_ms": 5,
            "connections_active": 3,
            "connections_max": 20
        },
        "redis": {
            "status": "healthy",
            "latency_ms": 1,
            "memory_used_mb": 128,
            "connected_clients": 5
        },
        "minio": {
            "status": "healthy",
            "buckets_accessible": true,
            "storage_used_gb": 45.2
        },
        "gpu": {
            "status": "healthy",
            "available": true,
            "name": "NVIDIA GeForce RTX 4080",
            "vram_total_gb": 16.0,
            "vram_used_gb": 4.5,
            "vram_free_gb": 11.5,
            "temperature_celsius": 45
        },
        "disk": {
            "status": "healthy",
            "total_gb": 500,
            "used_gb": 120,
            "free_gb": 380,
            "percent_used": 24
        }
    },
    "timestamp": "2024-11-30T10:30:00Z"
}
```

---

### 3. Circuit Breaker Status

**GET** `/api/v1/health/circuit-breakers`

Status aller OCR-Backend Circuit Breakers.

**Response:**
```json
{
    "status": "healthy",
    "circuit_breakers": {
        "deepseek": {
            "state": "CLOSED",
            "failure_count": 0,
            "success_count": 150,
            "last_failure": null,
            "last_success": "2024-11-30T10:25:00Z",
            "failure_rate": 0.0,
            "is_available": true
        },
        "got_ocr": {
            "state": "HALF_OPEN",
            "failure_count": 3,
            "success_count": 45,
            "last_failure": "2024-11-30T10:15:00Z",
            "last_success": "2024-11-30T10:20:00Z",
            "failure_rate": 0.062,
            "is_available": true
        },
        "surya": {
            "state": "OPEN",
            "failure_count": 5,
            "success_count": 10,
            "last_failure": "2024-11-30T10:28:00Z",
            "last_success": "2024-11-30T09:00:00Z",
            "failure_rate": 0.33,
            "is_available": false,
            "recovery_at": "2024-11-30T10:33:00Z"
        }
    },
    "summary": {
        "total_breakers": 3,
        "closed": 1,
        "half_open": 1,
        "open": 1,
        "available_backends": ["deepseek", "got_ocr"]
    },
    "timestamp": "2024-11-30T10:30:00Z"
}
```

**Circuit Breaker States:**

| State | Beschreibung |
|-------|-------------|
| `CLOSED` | Normal - Anfragen werden durchgelassen |
| `OPEN` | Ausgefallen - Anfragen werden blockiert |
| `HALF_OPEN` | Testphase - Einzelne Anfragen zur Prüfung |

---

### 4. OCR Pipeline Status

**GET** `/api/v1/health/pipeline`

Vollständiger Status der OCR-Pipeline inkl. Confidence Service und Fallback Chain.

**Response:**
```json
{
    "status": "healthy",
    "pipeline": {
        "confidence_service": {
            "status": "active",
            "thresholds": {
                "high": 0.85,
                "medium": 0.60,
                "low": 0.40
            },
            "current_stats": {
                "total_processed": 1250,
                "high_confidence": 890,
                "medium_confidence": 280,
                "low_confidence": 80,
                "average_confidence": 0.78
            }
        },
        "fallback_chain": {
            "status": "active",
            "chain_order": ["deepseek", "got_ocr", "surya"],
            "available_backends": ["deepseek", "got_ocr"],
            "fallback_stats": {
                "total_fallbacks": 45,
                "successful_fallbacks": 42,
                "fallback_success_rate": 0.93
            }
        },
        "active_jobs": {
            "pending": 5,
            "processing": 2,
            "queued": 12
        }
    },
    "recommendations": [],
    "timestamp": "2024-11-30T10:30:00Z"
}
```

---

### 5. SLO/SLI Status

**GET** `/api/v1/health/slo`

Service Level Objectives und Indicators.

**Response:**
```json
{
    "status": "healthy",
    "slo": {
        "availability": {
            "target": 0.999,
            "current": 0.9995,
            "status": "met",
            "period": "30d",
            "error_budget_remaining": 0.85
        },
        "latency_p95": {
            "target_ms": 2000,
            "current_ms": 1450,
            "status": "met",
            "period": "1h"
        },
        "latency_p99": {
            "target_ms": 5000,
            "current_ms": 3200,
            "status": "met",
            "period": "1h"
        },
        "quality": {
            "target_confidence": 0.70,
            "current_confidence": 0.78,
            "status": "met",
            "period": "24h"
        },
        "throughput": {
            "target_per_hour": 500,
            "current_per_hour": 620,
            "status": "met",
            "period": "1h"
        }
    },
    "alerts": [],
    "timestamp": "2024-11-30T10:30:00Z"
}
```

**SLO Status Werte:**

| Status | Beschreibung |
|--------|-------------|
| `met` | SLO wird eingehalten |
| `at_risk` | SLO gefährdet (Error Budget < 20%) |
| `violated` | SLO verletzt |

---

### 6. GPU Memory Guard Status

**GET** `/api/v1/health/gpu-memory`

Detaillierter GPU-Speicherstatus und Guard-Metriken.

**Response:**
```json
{
    "status": "healthy",
    "memory": {
        "available": true,
        "allocated_gb": 4.5,
        "reserved_gb": 6.0,
        "total_gb": 16.0,
        "limit_gb": 13.6,
        "usage_percent": 28.1,
        "remaining_gb": 9.1,
        "status_level": "ok"
    },
    "guard": {
        "config": {
            "limit_gb": 13.6,
            "warning_threshold": 0.75,
            "critical_threshold": 0.90,
            "auto_cleanup": true
        },
        "metrics": {
            "cleanup_count": 12,
            "enforcement_count": 3,
            "warning_count": 25,
            "critical_count": 2
        }
    },
    "recommendations": [],
    "timestamp": "2024-11-30T10:30:00Z"
}
```

**Memory Status Levels:**

| Level | Beschreibung | VRAM Nutzung |
|-------|-------------|--------------|
| `ok` | Normal | < 75% vom Limit |
| `warning` | Erhöht | 75-90% vom Limit |
| `critical` | Kritisch | > 90% vom Limit |

---

### 7. Vollständiger Health Check

**GET** `/api/v1/health/complete`

Aggregiert alle Health-Checks mit Problemen und Empfehlungen.

**Response:**
```json
{
    "status": "degraded",
    "components": {
        "database": "healthy",
        "redis": "healthy",
        "minio": "healthy",
        "gpu": "healthy",
        "circuit_breakers": "degraded",
        "pipeline": "healthy",
        "slo": "healthy",
        "memory_guard": "healthy"
    },
    "problems": [
        {
            "component": "circuit_breakers",
            "severity": "warning",
            "message": "Surya OCR Backend ist ausgefallen",
            "since": "2024-11-30T10:28:00Z"
        }
    ],
    "recommendations": [
        "Surya Backend prüfen und ggf. neu starten",
        "Fallback auf DeepSeek und GOT-OCR aktiv"
    ],
    "uptime_seconds": 86400,
    "timestamp": "2024-11-30T10:30:00Z"
}
```

---

## Prometheus Metriken

### HTTP Metriken

Die PrometheusMiddleware erfasst automatisch:

```
# Anfragen gesamt
http_requests_total{method="GET", endpoint="/api/v1/health", status="200"} 1523

# Request-Dauer (Histogram)
http_request_duration_seconds_bucket{method="POST", endpoint="/api/v1/ocr/process", le="0.5"} 850
http_request_duration_seconds_sum{method="POST", endpoint="/api/v1/ocr/process"} 425.6
http_request_duration_seconds_count{method="POST", endpoint="/api/v1/ocr/process"} 1000

# Aktive Anfragen
http_requests_in_progress{method="POST", endpoint="/api/v1/ocr/process"} 2

# Fehler
http_errors_total{method="POST", endpoint="/api/v1/ocr/process", status="500"} 3

# Langsame Anfragen (> 5s)
http_slow_requests_total{method="POST", endpoint="/api/v1/ocr/process"} 15
```

### OCR Pipeline Metriken

```
# OCR Verarbeitung
ocr_processing_total{backend="deepseek", status="success"} 890
ocr_processing_duration_seconds{backend="deepseek", quantile="0.95"} 1.45

# Confidence
ocr_confidence_level{level="high"} 890
ocr_confidence_level{level="medium"} 280
ocr_confidence_level{level="low"} 80

# Fallbacks
ocr_fallback_total{from="deepseek", to="got_ocr"} 25
ocr_fallback_success_total 42
```

### GPU Metriken

```
# GPU Speicher
gpu_memory_allocated_bytes 4831838208
gpu_memory_reserved_bytes 6442450944
gpu_memory_limit_bytes 14603345920
gpu_memory_usage_ratio 0.281

# Memory Guard
gpu_memory_guard_cleanups_total 12
gpu_memory_guard_enforcements_total 3
gpu_memory_guard_warnings_total 25
gpu_memory_guard_critical_total 2
gpu_memory_status 0  # 0=ok, 1=warning, 2=critical
```

### Circuit Breaker Metriken

```
# Status pro Backend
circuit_breaker_state{backend="deepseek"} 0  # 0=CLOSED, 1=HALF_OPEN, 2=OPEN
circuit_breaker_failures{backend="deepseek"} 0
circuit_breaker_successes{backend="deepseek"} 150
circuit_breaker_failure_rate{backend="deepseek"} 0.0
```

---

## Grafana Dashboards

### OCR Pipeline Dashboard

Dashboard ID: `ablage-ocr-pipeline`

**Panels:**
1. SLO Status (Gauge-Panel)
2. Circuit Breaker Status (Stat-Panel)
3. Confidence Distribution (Pie Chart)
4. Fallback Rate (Time Series)
5. GPU Memory Usage (Gauge)
6. Request Rate (Time Series)
7. Error Rate (Time Series)
8. Latency P95/P99 (Time Series)

### Alerts

| Alert | Schwellwert | Beschreibung |
|-------|-------------|--------------|
| `HighErrorRate` | > 1% | Fehlerrate zu hoch |
| `HighLatencyP95` | > 3s | Latenz zu hoch |
| `GPUMemoryCritical` | > 90% | GPU-Speicher kritisch |
| `CircuitBreakerOpen` | state=2 | Backend ausgefallen |
| `LowConfidence` | < 0.6 avg | OCR-Qualität niedrig |
| `SLOViolation` | budget < 0 | SLO verletzt |

---

## Nutzungsbeispiele

### Kubernetes Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

### Kubernetes Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /api/v1/health/detailed
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

### Load Balancer Health Check

```bash
curl -s http://localhost:8000/api/v1/health | jq '.status'
```

### Monitoring Script

```python
import httpx
import asyncio

async def check_system_health():
    async with httpx.AsyncClient() as client:
        # Basis-Check
        health = await client.get("http://localhost:8000/api/v1/health")

        if health.json()["status"] != "healthy":
            # Detaillierte Analyse
            complete = await client.get(
                "http://localhost:8000/api/v1/health/complete"
            )
            data = complete.json()

            for problem in data.get("problems", []):
                print(f"PROBLEM: {problem['component']} - {problem['message']}")

            for rec in data.get("recommendations", []):
                print(f"EMPFEHLUNG: {rec}")
```

---

## Fehlerbehebung

### Circuit Breaker im OPEN State

1. Logs prüfen: `docker-compose logs -f backend worker`
2. GPU Status prüfen: `nvidia-smi`
3. Backend manuell testen
4. Ggf. Service neustarten

### GPU Memory Warning

1. Aktive Jobs prüfen
2. Cache leeren: `torch.cuda.empty_cache()`
3. Batch-Größe reduzieren
4. Ggf. Worker neustarten

### SLO Violation

1. Error Rate prüfen
2. Latenz-Verteilung analysieren
3. Backend-Auswahl überprüfen
4. Ressourcen skalieren

---

## Siehe auch

- [API Dokumentation](./API_Documentation.md)
- [Grafana Konfiguration](../Guides/Grafana_Config.md)
- [Metrics & Monitoring Guide](../Guides/Metrics-Monitoring-Guide.md)
- [Troubleshooting Guide](../Guides/Troubleshooting-Guide.md)
