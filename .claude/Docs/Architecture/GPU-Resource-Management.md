# GPU Resource Management Architecture

> **Enterprise GPU-Management für OCR-Workloads**
>
> Vollständige Dokumentation des GPU-Resource-Managements für RTX 4080 (16GB VRAM).

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [GPUManager Klasse](#2-gpumanager-klasse)
3. [GPUMemoryGuard](#3-gpumemoryguard)
4. [Adaptive Batch Processing](#4-adaptive-batch-processing)
5. [Distributed GPU Locking](#5-distributed-gpu-locking)
6. [OOM Recovery Patterns](#6-oom-recovery-patterns)
7. [GPU Metrics & Monitoring](#7-gpu-metrics--monitoring)
8. [API Backpressure](#8-api-backpressure)
9. [Best Practices](#9-best-practices)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Übersicht

### Hardware-Spezifikation

```
┌─────────────────────────────────────────────────────────────────┐
│                    NVIDIA RTX 4080 Configuration                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Total VRAM:          16 GB                                     │
│  Usable (85%):        13.6 GB                                   │
│  Safety Buffer:       2.4 GB (15%)                              │
│  CUDA Version:        12.x                                      │
│  cuDNN Version:       8.9+                                      │
│                                                                  │
│  Memory Thresholds:                                             │
│  ├── Safe:            < 70%  (< 11.2 GB)                        │
│  ├── Warning:         70-85% (11.2-13.6 GB)                     │
│  ├── Critical:        85-90% (13.6-14.4 GB)                     │
│  └── Reject:          > 90%  (> 14.4 GB)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Backend VRAM Requirements

| Backend | VRAM (GB) | Quantization | Use Case |
|---------|-----------|--------------|----------|
| DeepSeek-Janus-Pro | 12.0 | 4-bit | Best German OCR |
| GOT-OCR 2.0 | 10.0 | FP16 | Tables, Formulas |
| Surya GPU | 8.0 | FP16 | Layout Analysis |
| Donut | 8.0 | FP16 | Vision Encoder |
| Chandra 9B | 15.0 | FP16 | Full VLM |
| Chandra 8-bit | 9.0 | 8-bit | Quantized VLM |
| Chandra 4-bit | 5.0 | 4-bit | Compact VLM |
| OlmOCR-2 7B | 14.0 | FP16 | Alternative |
| Surya CPU | 0.0 | - | Fallback |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   GPU Resource Management Stack                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: API Backpressure                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ GPUBackpressureMiddleware                                 │  │
│  │ → 70% Warn | 80% Queue | 90% Reject                       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  Layer 2: Memory Guard                                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ GPUMemoryGuard                                            │  │
│  │ → Limit Enforcement | Proactive Cleanup | Monitoring      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  Layer 3: Resource Manager                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ GPUManager                                                │  │
│  │ → Allocation | Batch Sizing | Memory Prediction           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  Layer 4: Distributed Locking                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Redis GPU Lock                                            │  │
│  │ → Atomic Acquire | TTL Refresh | Safe Release             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  Layer 5: Adaptive Processing                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ AdaptiveBatchProcessor                                    │  │
│  │ → OOM Recovery | Hysteresis | Profiling                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  Layer 6: Recovery                                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ GPURecoveryManager                                        │  │
│  │ → Fallback Chain | Incident Reporting | Batch Reduction   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. GPUManager Klasse

**Datei**: `app/gpu_manager.py` (1839 Zeilen)

### Kernfunktionen

```python
class GPUManager:
    """
    Zentraler GPU-Ressourcenmanager für RTX 4080.

    Features:
    - Thread-safe Allocation Tracking
    - Dynamic Batch Sizing mit 15% Safety Buffer
    - VRAM Prediction und proaktive OOM-Prävention
    """

    # RTX 4080 Konfiguration
    total_vram_bytes = 16 * 1024 * 1024 * 1024  # 16GB
    safety_buffer_bytes = 2 * 1024 * 1024 * 1024  # 2GB

    # Backend Requirements (GB)
    backend_requirements = {
        "deepseek": 12.0,
        "got_ocr": 10.0,
        "surya_gpu": 8.0,
        "donut": 8.0,
        "surya": 0.0  # CPU-only
    }
```

### Hauptmethoden

#### check_availability()

```python
def check_availability(self) -> Dict[str, Any]:
    """
    Prüft GPU-Verfügbarkeit und Status.

    Returns:
        {
            "available": bool,
            "device_name": str,
            "total_vram_gb": float,
            "free_vram_gb": float,
            "used_vram_gb": float,
            "safety_status": "safe" | "warning" | "critical"
        }
    """
```

#### allocate_for_backend()

```python
def allocate_for_backend(self, backend: str) -> Dict[str, Any]:
    """
    Allokiert GPU-Ressourcen für ein Backend.

    Features:
    - Thread-safe mit Lock
    - Automatische Cache-Bereinigung
    - Pre-check auf VRAM-Suffizenz

    Args:
        backend: Name des OCR-Backends

    Returns:
        {
            "success": bool,
            "allocated_gb": float,
            "remaining_gb": float,
            "recommendation": str | None
        }
    """
```

#### get_optimal_batch_size()

```python
def get_optimal_batch_size(
    self,
    backend: str,
    document_size_mb: float = 5.0
) -> int:
    """
    Berechnet optimale Batch-Größe mit 15% Safety Buffer.

    Algorithm:
    1. Free VRAM ermitteln
    2. 15% Safety Buffer abziehen
    3. Memory per Document berechnen
    4. Batch Size = safe_free / memory_per_doc

    Memory Heuristics:
    - DeepSeek: 1 GB/doc
    - GOT-OCR: 500 MB/doc
    - Surya GPU: 250 MB/doc
    - Hybrid: 1 GB/doc (conservative)

    Returns:
        Optimale Batch-Größe (1-32)
    """
```

**Formel**:
```
safe_free_gb = free_gb * (1 - 0.15)
batch_size = floor(safe_free_gb / memory_per_doc_gb)
batch_size = clamp(batch_size, 1, 32)
```

#### predict_memory_usage()

```python
def predict_memory_usage(
    self,
    backend: str,
    batch_size: int,
    image_size_mb: float = 5.0,
    num_pages: int = 1
) -> Dict[str, float]:
    """
    Prognostiziert Speicherverbrauch.

    Breakdown:
    - model_base_gb: Backend-Modell Basisverbrauch
    - processing_gb: Verarbeitungs-Overhead
    - overhead_gb: CUDA/Kernel Overhead

    Returns:
        {
            "total_gb": float,
            "model_base_gb": float,
            "processing_gb": float,
            "overhead_gb": float,
            "confidence": float  # 0-1
        }
    """
```

#### can_process_task()

```python
def can_process_task(
    self,
    backend: str,
    batch_size: int,
    document_size_mb: float = 5.0
) -> Dict[str, Any]:
    """
    Prüft ob Task verarbeitet werden kann.

    Features:
    - Proaktive OOM-Prävention
    - Alternative Backend-Vorschläge
    - Maximum Batch Size Berechnung

    Returns:
        {
            "can_process": bool,
            "reason": str,
            "suggested_backend": str | None,
            "max_batch_size": int
        }
    """
```

---

## 3. GPUMemoryGuard

**Datei**: `app/gpu_manager.py` (Zeilen 831-1305)

### Konfiguration

```python
class GPUMemoryGuard:
    """
    Erzwingt VRAM-Limits und überwacht Speicher.

    Thresholds:
    - DEFAULT_LIMIT_GB:        13.6 (85% von 16GB)
    - WARNING_THRESHOLD:       0.75 (75%)
    - CRITICAL_THRESHOLD:      0.90 (90%)
    - PROACTIVE_CLEANUP:       0.80 (80%)
    """

    DEFAULT_LIMIT_GB = 13.6
    WARNING_THRESHOLD = 0.75
    CRITICAL_THRESHOLD = 0.90
    PROACTIVE_CLEANUP_THRESHOLD = 0.80
```

### Hauptmethoden

#### check_memory_status()

```python
def check_memory_status(self) -> Dict[str, Any]:
    """
    Prüft aktuellen Speicherstatus.

    Returns:
        {
            "allocated_gb": float,
            "reserved_gb": float,
            "total_gb": float,
            "usage_ratio": float,
            "status": "ok" | "warning" | "critical"
        }
    """
```

#### can_allocate()

```python
def can_allocate(self, required_gb: float) -> Dict[str, Any]:
    """
    Prüft ob Allokation möglich ist.

    Features:
    - Blockiert bei Limit-Überschreitung
    - Auto-Cleanup bei Violation
    - Fallback-Empfehlungen

    Returns:
        {
            "allowed": bool,
            "current_usage_gb": float,
            "limit_gb": float,
            "fallback_recommendation": str | None
        }
    """
```

#### cleanup_cache()

```python
def cleanup_cache(self) -> int:
    """
    Bereinigt GPU-Cache.

    Steps:
    1. torch.cuda.empty_cache()
    2. gc.collect()
    3. torch.cuda.synchronize()

    Returns:
        Freigegebene Bytes
    """
```

### Background Monitor

```python
def start_memory_monitor(self, interval_seconds: int = 10):
    """
    Startet Hintergrund-Monitoring.

    Features:
    - Prüft VRAM alle 10 Sekunden
    - Proaktive Bereinigung bei 80%
    - Logging bei Status-Änderungen
    """

async def _proactive_memory_check(self):
    """
    Proaktive Bereinigung BEVOR Warning-Threshold erreicht.

    Trigger: 80% Auslastung
    Action: Cache leeren, GC triggern
    Benefit: Verhindert Kaskaden-Effekte
    """
```

---

## 4. Adaptive Batch Processing

**Datei**: `app/gpu_manager.py` (Zeilen 1362-1634)

### Konfiguration

```python
class AdaptiveBatchProcessor:
    """
    Adaptives Batch-Processing mit OOM-Recovery.

    Configuration:
    - INITIAL_BATCH:     4
    - MIN_BATCH:         1
    - MAX_BATCH:         8
    - HYSTERESIS_THRESHOLD: 100 Erfolge vor Erhöhung
    - INCREASE_FACTOR:   1.1 (+10%)
    """

    DEFAULT_INITIAL_BATCH = 4
    MIN_BATCH_SIZE = 1
    MAX_BATCH_SIZE = 8
    HYSTERESIS_SUCCESS_THRESHOLD = 100
    HYSTERESIS_INCREASE_FACTOR = 1.1
```

### Algorithmus

```
┌─────────────────────────────────────────────────────────────────┐
│              Adaptive Batch Processing Algorithm                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Für jeden Batch:                                               │
│                                                                  │
│  1. Versuche Verarbeitung mit current_batch_size                │
│     │                                                            │
│     ├── SUCCESS:                                                │
│     │   ├── Profiling: GPU-Speicher messen                      │
│     │   ├── Track consecutive_successes++                       │
│     │   │                                                        │
│     │   └── if consecutive_successes >= 100:                    │
│     │       └── batch_size *= 1.1 (Hysteresis)                  │
│     │                                                            │
│     └── OOM ERROR:                                              │
│         ├── batch_size /= 2 (Halbieren)                         │
│         ├── consecutive_successes = 0                           │
│         ├── effective_max_batch verringern                      │
│         ├── torch.cuda.empty_cache()                            │
│         └── Retry mit kleinerer Batch                           │
│                                                                  │
│  2. if batch_size < 1:                                          │
│     └── RuntimeError: "Minimum batch size reached"              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### process_with_fallback()

```python
async def process_with_fallback(
    self,
    documents: List[Document],
    processor: Callable
) -> ProcessingResult:
    """
    Verarbeitet Dokumente mit adaptiver Batch-Größe.

    Features:
    - Automatische OOM-Recovery
    - Hysteresis für stabile Batch-Größen
    - Memory-Profiling pro Batch

    Algorithm:
    1. Starte mit current_batch_size
    2. Bei Erfolg: Profile, track successes
    3. Bei 100+ Erfolgen: Batch +10%
    4. Bei OOM: Batch /2, retry
    5. Bei batch < 1: Raise error
    """
```

### Statistiken

```python
def get_stats(self) -> Dict[str, Any]:
    """
    Returns:
        {
            "total_batches": int,
            "successful_batches": int,
            "oom_events": int,
            "fallback_count": int,
            "oom_rate": float,
            "success_rate": float,
            "consecutive_successes_since_oom": int,
            "hysteresis_increases": int,
            "current_effective_max_batch": int
        }
    """
```

---

## 5. Distributed GPU Locking

**Datei**: `app/workers/celery_app.py` (Zeilen 30-168)

### Konfiguration

```python
# Redis-basiertes GPU-Locking
_GPU_LOCK_KEY = "ablage:gpu:lock"
_GPU_LOCK_TIMEOUT = 60          # Auto-Release nach 60s
_GPU_LOCK_ACQUIRE_TIMEOUT = 30  # Max Wartezeit
_GPU_LOCK_RETRY_INTERVAL = 0.1  # 100ms Retry-Interval
```

### Lock-Mechanismus

```
┌─────────────────────────────────────────────────────────────────┐
│                   Distributed GPU Lock Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Worker A                     Redis                Worker B      │
│     │                          │                      │          │
│     │── SET ablage:gpu:lock ──▶│                      │          │
│     │   NX, EX=60              │                      │          │
│     │◀── OK ──────────────────│                      │          │
│     │                          │                      │          │
│     │   [Processing...]        │◀── SET ... NX ──────│          │
│     │                          │── nil (blocked) ────▶│          │
│     │                          │                      │          │
│     │── SET ... XX EX=60 ─────▶│   [Retry 100ms]     │          │
│     │   (Refresh Lock)         │◀── SET ... NX ──────│          │
│     │                          │── nil ──────────────▶│          │
│     │                          │                      │          │
│     │── DEL ablage:gpu:lock ──▶│                      │          │
│     │   (if owner)             │                      │          │
│     │                          │◀── SET ... NX ──────│          │
│     │                          │── OK ───────────────▶│          │
│     │                          │                      │          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### acquire_gpu_lock()

```python
def acquire_gpu_lock(timeout: float = 30.0) -> Optional[str]:
    """
    Akquiriert GPU-Lock mit Retry und Backoff.

    Features:
    - Atomic SET NX (nur wenn nicht existiert)
    - Auto-Expire nach 60s
    - 100ms Retry-Intervall
    - Exponential Backoff bei Redis-Fehlern

    Backoff Formula:
        base_delay = 0.1 * (2 ** min(attempt, 5))  # Max 3.2s
        jitter = random(0, base_delay * 0.5)
        delay = min(base_delay + jitter, 5.0)

    Returns:
        lock_value (UUID) bei Erfolg, None bei Timeout
    """
```

### refresh_gpu_lock()

```python
def refresh_gpu_lock(lock_value: str) -> bool:
    """
    Verlängert Lock-TTL für lang laufende Tasks.

    Features:
    - Verifiziert Lock-Ownership vor Refresh
    - Wird alle 25s aufgerufen (vor 60s Expiration)

    Returns:
        True bei Erfolg, False wenn Lock verloren
    """
```

### Integration in OCR Tasks

```python
# app/workers/tasks/ocr_tasks.py

async def _periodic_lock_refresh(task, interval: int = 25):
    """
    Hintergrund-Task für Lock-Refresh.

    Interval: 25s (konservativ vor 60s TTL)
    """
    while True:
        await asyncio.sleep(interval)
        refreshed = await loop.run_in_executor(
            None, task.refresh_lock
        )
        if not refreshed:
            logger.warning("gpu_lock_lost", task_id=task.request.id)
            break
```

---

## 6. OOM Recovery Patterns

**Datei**: `app/core/gpu_recovery.py` (537 Zeilen)

### Konfiguration

```python
BACKEND_CONFIGS = {
    "deepseek": BackendConfig(
        default_batch_size=4,
        min_batch_size=1,
        max_batch_size=8,
        vram_gb=12.0,
        reduction_factor=0.5
    ),
    "got_ocr": BackendConfig(
        default_batch_size=8,
        min_batch_size=1,
        max_batch_size=16,
        vram_gb=10.0,
        reduction_factor=0.5
    ),
    "surya_gpu": BackendConfig(
        default_batch_size=16,
        min_batch_size=2,
        max_batch_size=32,
        vram_gb=8.0,
        reduction_factor=0.5
    )
}

MAX_VRAM_USAGE_GB = 13.6  # 85% von 16GB
```

### GPURecoveryManager

```python
class GPURecoveryManager:
    """
    Zentraler OOM-Recovery-Manager.

    Features:
    - Pre-Processing Memory Check
    - Inkrementelle Batch-Erhöhung bei Erfolg
    - Batch-Reduktion bei OOM (50%)
    - Security: Incident-Report bei wiederholten OOM
    """
```

### execute_with_oom_recovery()

```python
async def execute_with_oom_recovery(
    self,
    backend: str,
    documents: List[Document],
    processor: Callable
) -> ProcessingResult:
    """
    Führt Verarbeitung mit OOM-Recovery aus.

    Algorithm:
    1. Pre-Check: VRAM > 85%? → Cache leeren
    2. Verarbeite Batch
    3. Bei Erfolg: Batch inkrementell erhöhen
    4. Bei OOM: Batch /= reduction_factor (0.5)
    5. Security: >2 consecutive OOM oder >5 total → Incident

    Incident Report Triggers:
    - > 2 aufeinanderfolgende OOM
    - > 5 OOM insgesamt
    """
```

### Memory Stats

```python
@dataclass
class GPUMemoryStats:
    total_gb: float
    allocated_gb: float
    cached_gb: float
    free_gb: float
    utilization_percent: float

def get_memory_stats(self) -> GPUMemoryStats:
    """Aktuelle GPU-Speicherstatistiken."""
```

### Fallback-Kette

```
┌─────────────────────────────────────────────────────────────────┐
│                    OCR Fallback Chain                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Priority 1: DeepSeek-Janus-Pro (12GB)                          │
│     │                                                            │
│     └── OOM? ──▶ Priority 2: GOT-OCR 2.0 (10GB)                │
│                      │                                           │
│                      └── OOM? ──▶ Priority 3: Surya GPU (8GB)   │
│                                       │                          │
│                                       └── OOM? ──▶ Surya CPU    │
│                                                    (0GB, slow)   │
│                                                                  │
│  Fallback Selection Criteria:                                   │
│  - Available VRAM                                                │
│  - Document Complexity                                           │
│  - Quality Requirements                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. GPU Metrics & Monitoring

**Datei**: `app/services/gpu_metrics_service.py` (700 Zeilen)

### Prometheus Metriken

#### Hardware Metrics

```python
# Speicher-Metriken
ablage_gpu_memory_used_bytes = Gauge(
    "ablage_gpu_memory_used_bytes",
    "GPU memory currently used"
)
ablage_gpu_memory_total_bytes = Gauge(
    "ablage_gpu_memory_total_bytes",
    "Total GPU memory available"
)
ablage_gpu_memory_percent = Gauge(
    "ablage_gpu_memory_percent",
    "GPU memory utilization percentage"
)
ablage_gpu_available = Gauge(
    "ablage_gpu_available",
    "GPU availability status (1=available, 0=unavailable)"
)
```

#### OCR Processing Metrics

```python
# Request-Metriken
ablage_ocr_requests_total = Counter(
    "ablage_ocr_requests_total",
    "Total OCR requests",
    ["backend", "status"]
)
ablage_ocr_processing_duration_seconds = Histogram(
    "ablage_ocr_processing_duration_seconds",
    "OCR processing time",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)
ablage_ocr_batch_size = Histogram(
    "ablage_ocr_batch_size",
    "Batch sizes used for OCR",
    buckets=[1, 2, 4, 8, 16, 32, 64]
)
```

#### OOM & Recovery Metrics

```python
# OOM-Ereignisse
ablage_gpu_oom_errors_total = Counter(
    "ablage_gpu_oom_errors_total",
    "Total GPU OOM errors"
)
ablage_gpu_oom_recoveries_total = Counter(
    "ablage_gpu_oom_recoveries_total",
    "Successful OOM recoveries",
    ["strategy"]  # batch_reduction, backend_fallback, cpu_fallback
)
ablage_gpu_memory_cleanups_total = Counter(
    "ablage_gpu_memory_cleanups_total",
    "Memory cleanup operations",
    ["trigger"]  # proactive, reactive, manual
)
```

#### Adaptive Batch Metrics

```python
# Hysteresis-Tracking
ablage_adaptive_batch_consecutive_successes = Gauge(
    "ablage_adaptive_batch_consecutive_successes",
    "Consecutive successful batches since last OOM"
)
ablage_adaptive_batch_effective_max = Gauge(
    "ablage_adaptive_batch_effective_max",
    "Current effective maximum batch size"
)
ablage_adaptive_batch_hysteresis_increases = Counter(
    "ablage_adaptive_batch_hysteresis_increases",
    "Number of hysteresis-triggered batch increases"
)
```

### GPUMetricsService

```python
class GPUMetricsService:
    """
    Prometheus-Metriken für GPU-Monitoring.

    Features:
    - Separate Registry (GPU_REGISTRY)
    - Thread-safe Updates
    - Background Auto-Update
    - Helper-Funktionen für Recording
    """

    def __init__(self, auto_update_interval: int = 10):
        self._lock = threading.Lock()
        self._update_thread = None

    def start_auto_update(self):
        """Startet Background-Thread für Metriken-Updates."""

    def record_ocr_request(
        self,
        backend: str,
        status: str,
        duration_seconds: float,
        batch_size: int
    ):
        """Zeichnet OCR-Request auf."""
```

### Grafana Dashboard

**Dashboard**: `ablage-gpu-monitoring`

```
┌─────────────────────────────────────────────────────────────────┐
│                    GPU Monitoring Dashboard                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Row 1: Overview                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ VRAM Used %     │  │ OOM Events/h    │  │ Batch Size Avg  │ │
│  │     67%         │  │      0.2        │  │      4.3        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                  │
│  Row 2: Memory Timeline                                         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  [VRAM Usage Graph - 24h]                                   ││
│  │  Warning Line: 75% ─────────────────────────────            ││
│  │  Critical Line: 90% ────────────────────────────            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Row 3: Processing                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐│
│  │ OCR Duration Histogram   │  │ Requests by Backend          ││
│  │ [Histogram]              │  │ DeepSeek: 65%                ││
│  │                          │  │ GOT-OCR: 30%                 ││
│  │                          │  │ Surya: 5%                    ││
│  └──────────────────────────┘  └──────────────────────────────┘│
│                                                                  │
│  Row 4: Recovery                                                │
│  ┌──────────────────────────────────────────────────────────────┐
│  │ OOM Events & Recoveries                                     ││
│  │ [Stacked Bar: OOM, Recovered, Fallback]                     ││
│  └──────────────────────────────────────────────────────────────┘
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. API Backpressure

**Datei**: `app/middleware/gpu_backpressure.py` (300 Zeilen)

### Konfiguration

```python
# VRAM Thresholds
VRAM_THRESHOLD_WARN = 0.70    # 70% - Log Warning
VRAM_THRESHOLD_QUEUE = 0.80   # 80% - Queue Request
VRAM_THRESHOLD_REJECT = 0.90  # 90% - Reject Request

# Timing
MAX_QUEUE_WAIT = 30.0         # Max Queue-Wartezeit
VRAM_CHECK_INTERVAL = 1.0     # Prüfintervall
```

### Strategie

```
┌─────────────────────────────────────────────────────────────────┐
│                   GPU Backpressure Strategy                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  VRAM < 70%:                                                    │
│  └── ✅ Process immediately                                     │
│                                                                  │
│  VRAM 70-80%:                                                   │
│  └── ⚠️ Log warning, process with caution                       │
│                                                                  │
│  VRAM 80-90%:                                                   │
│  └── ⏳ Queue request, wait up to 30s for VRAM to free          │
│       └── If freed: Process                                     │
│       └── If timeout: 503 Service Unavailable                   │
│                                                                  │
│  VRAM > 90%:                                                    │
│  └── ❌ Immediate 503 Service Unavailable                       │
│       Headers:                                                   │
│       - Retry-After: 30                                         │
│       - X-GPU-VRAM-Usage: <percent>                             │
│       - X-GPU-VRAM-Available-GB: <gb>                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Response Headers

```python
# Bei Ablehnung
headers = {
    "Retry-After": "30",
    "X-GPU-VRAM-Usage": f"{usage_percent:.1f}",
    "X-GPU-VRAM-Available-GB": f"{available_gb:.2f}"
}
```

---

## 9. Best Practices

### 9.1 Memory Management

```python
# ✅ GPU Context Manager verwenden
from app.gpu_manager import gpu_memory_guard

with gpu_memory_guard(threshold_gb=13.6):
    result = ocr_backend.process(documents)
# Automatische Cache-Bereinigung bei Überschreitung

# ✅ Explizite Cache-Bereinigung nach großen Batches
torch.cuda.empty_cache()
gc.collect()
torch.cuda.synchronize()

# ❌ Vermeiden: Unbegrenztes Batch-Processing
for doc in all_documents:  # Kann OOM verursachen
    process(doc)
```

### 9.2 Batch Sizing

```python
# ✅ Dynamische Batch-Größe
gpu_manager = GPUManager()
batch_size = gpu_manager.get_optimal_batch_size(
    backend="deepseek",
    document_size_mb=avg_doc_size
)

# ✅ Prädiktive Speicherprüfung
prediction = gpu_manager.predict_memory_usage(
    backend="deepseek",
    batch_size=4,
    image_size_mb=10.0
)
if prediction["total_gb"] > 13.6:
    batch_size = batch_size // 2

# ❌ Vermeiden: Feste Batch-Größen
BATCH_SIZE = 16  # Kann OOM bei großen Dokumenten
```

### 9.3 Lock Management

```python
# ✅ Lock mit Timeout und Cleanup
lock_value = acquire_gpu_lock(timeout=30.0)
if lock_value is None:
    raise GPUBusyError("GPU lock acquisition timeout")

try:
    # Start refresh thread für lange Tasks
    refresh_task = asyncio.create_task(
        _periodic_lock_refresh(self, interval=25)
    )

    result = await process_with_gpu(documents)

finally:
    refresh_task.cancel()
    release_gpu_lock(lock_value)

# ❌ Vermeiden: Lock ohne Refresh
lock = acquire_gpu_lock()
long_running_process()  # Lock kann expiren!
release_gpu_lock(lock)
```

### 9.4 Fallback Handling

```python
# ✅ Graceful Degradation
try:
    result = await deepseek_ocr.process(doc)
except torch.cuda.OutOfMemoryError:
    logger.warning("gpu_fallback", from_backend="deepseek")
    torch.cuda.empty_cache()

    try:
        result = await got_ocr.process(doc)
    except torch.cuda.OutOfMemoryError:
        logger.warning("gpu_fallback", from_backend="got_ocr")
        result = await surya_cpu.process(doc)  # CPU-Fallback

# ❌ Vermeiden: Keine Fallback-Logik
result = await deepseek_ocr.process(doc)  # Crash bei OOM
```

---

## 10. Troubleshooting

### 10.1 GPU nicht erkannt

```bash
# NVIDIA Treiber prüfen
nvidia-smi

# CUDA in Container prüfen
docker exec -it ablage-backend python -c \
    "import torch; print(torch.cuda.is_available())"

# Docker GPU-Zugriff prüfen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 10.2 OOM trotz freiem Speicher

```python
# Fragmentierung prüfen
import torch
print(f"Allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
print(f"Reserved:  {torch.cuda.memory_reserved() / 1e9:.2f} GB")
print(f"Max Allocated: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")

# Lösung: Cache leeren
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
```

### 10.3 Lock-Deadlock

```bash
# Redis Lock prüfen
redis-cli GET ablage:gpu:lock

# Lock manuell löschen (Notfall!)
redis-cli DEL ablage:gpu:lock

# Lock-Holder identifizieren
redis-cli GET ablage:gpu:lock | jq .  # Enthält Worker-ID
```

### 10.4 Langsame OCR-Verarbeitung

```python
# Profiling aktivieren
import cProfile
profiler = cProfile.Profile()
profiler.enable()
result = ocr_backend.process(image)
profiler.disable()
profiler.print_stats(sort='cumulative')

# GPU Bottleneck prüfen
import torch
torch.cuda.synchronize()
start = torch.cuda.Event(enable_timing=True)
end = torch.cuda.Event(enable_timing=True)
start.record()
result = ocr_backend.process(image)
end.record()
torch.cuda.synchronize()
print(f"GPU Time: {start.elapsed_time(end):.2f} ms")
```

### 10.5 Häufige OOM-Events

```bash
# Prometheus Query für OOM-Rate
rate(ablage_gpu_oom_errors_total[1h])

# Batch-Size-Verteilung
histogram_quantile(0.95, ablage_ocr_batch_size_bucket)

# Empfehlungen:
# 1. MAX_BATCH_SIZE reduzieren
# 2. PROACTIVE_CLEANUP_THRESHOLD auf 75% senken
# 3. Safety Buffer auf 20% erhöhen
```

---

## Konfigurationsreferenz

### Alle Parameter

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `GPU_LOCK_TIMEOUT` | 60s | Auto-Release bei Hang |
| `GPU_LOCK_ACQUIRE_TIMEOUT` | 30s | Max Lock-Wartezeit |
| `GPU_LOCK_RETRY_INTERVAL` | 0.1s | Retry-Intervall |
| `GPU_MEMORY_LIMIT_GB` | 13.6 | 85% von 16GB |
| `WARNING_THRESHOLD` | 75% | Warning bei Auslastung |
| `CRITICAL_THRESHOLD` | 90% | Critical bei Auslastung |
| `PROACTIVE_CLEANUP` | 80% | Background Cleanup |
| `MONITOR_INTERVAL` | 10s | Monitoring-Frequenz |
| `HYSTERESIS_THRESHOLD` | 100 | Erfolge vor Erhöhung |
| `HYSTERESIS_FACTOR` | 1.1 | +10% pro Erhöhung |
| `BATCH_CACHE_TTL` | 30s | Cache für Batch-Sizes |
| `SAFETY_BUFFER` | 15% | ~2.4GB immer frei |

### Datei-Referenz

| Datei | Zeilen | Funktion |
|-------|--------|----------|
| `app/gpu_manager.py` | 1839 | GPUManager, Guard, Adaptive |
| `app/core/gpu_recovery.py` | 537 | OOM Recovery |
| `app/services/batch_processor.py` | 810 | Batch Processing |
| `app/services/gpu_metrics_service.py` | 700 | Prometheus Metrics |
| `app/middleware/gpu_backpressure.py` | 300 | API Backpressure |
| `app/workers/celery_app.py` | 168 | GPU Locking |
| `app/workers/tasks/ocr_tasks.py` | 200+ | Lock Refresh |

---

**Letzte Aktualisierung**: Januar 2026
**Version**: 1.0
**Maintainer**: Ablage-System Team
