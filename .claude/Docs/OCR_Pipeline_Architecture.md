# OCR Pipeline Architektur

## Übersicht

Die OCR-Pipeline des Ablage-Systems ist eine robuste, fehlertolerante Verarbeitungskette für Dokumentendigitalisierung mit:

- **Multi-Backend Support**: DeepSeek, GOT-OCR, Surya
- **Confidence-basierte Qualitätssicherung**
- **Automatische Fallback-Mechanismen**
- **Circuit Breaker für Ausfallsicherheit**
- **GPU Memory Guard für Ressourcenschutz**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         OCR Pipeline Architektur                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │   Document   │───▶│   Fallback   │───▶│  Confidence  │              │
│  │    Input     │    │    Chain     │    │   Service    │              │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘              │
│                             │                    │                       │
│         ┌───────────────────┼────────────────────┼───────────────────┐  │
│         │                   ▼                    ▼                   │  │
│         │  ┌─────────────────────────────────────────────────────┐  │  │
│         │  │              Circuit Breaker Registry               │  │  │
│         │  └─────────────────────────────────────────────────────┘  │  │
│         │         │              │              │                    │  │
│         │         ▼              ▼              ▼                    │  │
│         │  ┌───────────┐  ┌───────────┐  ┌───────────┐             │  │
│         │  │ DeepSeek  │  │  GOT-OCR  │  │   Surya   │             │  │
│         │  │  Backend  │  │  Backend  │  │  Backend  │             │  │
│         │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘             │  │
│         │        │              │              │                    │  │
│         │        └──────────────┼──────────────┘                    │  │
│         │                       ▼                                   │  │
│         │         ┌─────────────────────────────┐                   │  │
│         │         │     GPU Memory Guard        │                   │  │
│         │         └─────────────────────────────┘                   │  │
│         │                       │                                   │  │
│         └───────────────────────┼───────────────────────────────────┘  │
│                                 ▼                                       │
│                    ┌─────────────────────────────┐                     │
│                    │     OCR Pipeline Result     │                     │
│                    └─────────────────────────────┘                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Komponenten

### 1. Confidence Service

**Pfad:** `app/services/confidence_service.py`

Der Confidence Service bewertet die Qualität der OCR-Ergebnisse und trifft Entscheidungen über Nachverarbeitung.

#### Konfiguration

```python
class ConfidenceThresholds:
    HIGH = 0.85      # Hohe Qualität, keine Nachbearbeitung nötig
    MEDIUM = 0.60    # Akzeptabel, optionale Nachbearbeitung
    LOW = 0.40       # Niedrig, Fallback empfohlen
```

#### Confidence Levels

| Level | Schwellwert | Beschreibung | Aktion |
|-------|-------------|--------------|--------|
| `HIGH` | ≥ 0.85 | Exzellente Qualität | Direkt speichern |
| `MEDIUM` | 0.60 - 0.84 | Akzeptable Qualität | Optionale Korrektur |
| `LOW` | 0.40 - 0.59 | Niedrige Qualität | Fallback versuchen |
| `VERY_LOW` | < 0.40 | Unzureichend | Manuell prüfen |

#### Nutzung

```python
from app.services.confidence_service import ConfidenceService, ConfidenceLevel

confidence_service = ConfidenceService()

# Confidence-Level bestimmen
level = confidence_service.determine_level(0.75)
# -> ConfidenceLevel.MEDIUM

# Qualitätsentscheidung treffen
decision = confidence_service.should_accept(
    confidence=0.82,
    backend="deepseek",
    min_acceptable=ConfidenceLevel.MEDIUM
)
# -> QualityDecision(accept=True, reason="confidence_acceptable")

# Token-Level Confidence extrahieren
token_confidences = confidence_service.extract_token_confidence(ocr_result)
# -> [0.95, 0.87, 0.45, 0.92, ...]

# Aggregierte Statistiken
stats = confidence_service.get_statistics()
# -> {"high": 890, "medium": 280, "low": 80, "average": 0.78}
```

---

### 2. Fallback Chain

**Pfad:** `app/services/fallback_chain.py`

Die Fallback Chain verwaltet die Reihenfolge der OCR-Backends und führt automatische Fallbacks bei Fehlern oder niedriger Qualität durch.

#### Standard-Reihenfolge

```python
DEFAULT_CHAIN = [
    "deepseek",   # Beste Qualität für deutsche Texte
    "got_ocr",    # Schnell, gut für Standarddokumente
    "surya",      # CPU-Fallback, Layout-Analyse
]
```

#### Fallback-Auslöser

1. **Backend-Fehler**: Exception während Verarbeitung
2. **Circuit Breaker OPEN**: Backend temporär deaktiviert
3. **Niedrige Confidence**: Ergebnis unter Schwellwert
4. **GPU OOM**: Speicherüberlauf

#### Nutzung

```python
from app.services.fallback_chain import FallbackChain

fallback_chain = FallbackChain()

# Nächstes verfügbares Backend holen
backend = fallback_chain.get_next_backend()
# -> "deepseek" (oder erstes verfügbares)

# Mit Fallback verarbeiten
result = await fallback_chain.execute_with_fallback(
    document=doc,
    min_confidence=0.60
)
# Versucht automatisch alle Backends bis Erfolg

# Fallback-Statistiken
stats = fallback_chain.get_fallback_stats()
# -> {"total": 45, "successful": 42, "rate": 0.93}
```

#### Fallback-Logik

```
┌─────────────┐
│   Start     │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ Backend 1 (DS)   │──────┐
└──────┬───────────┘      │ Fehler/Low Confidence
       │ Erfolg           │
       ▼                  ▼
┌──────────────────┐ ┌──────────────────┐
│    Ergebnis      │ │ Backend 2 (GOT)  │──────┐
└──────────────────┘ └──────┬───────────┘      │ Fehler
                            │ Erfolg           │
                            ▼                  ▼
                     ┌──────────────────┐ ┌──────────────────┐
                     │    Ergebnis      │ │ Backend 3 (Surya)│
                     └──────────────────┘ └──────┬───────────┘
                                                  │
                                                  ▼
                                          ┌──────────────────┐
                                          │ Ergebnis/Fehler  │
                                          └──────────────────┘
```

---

### 3. Circuit Breaker

**Pfad:** `app/services/circuit_breaker.py`

Der Circuit Breaker schützt das System vor kaskadierten Fehlern durch temporäre Deaktivierung fehlerhafter Backends.

#### States

```python
class CircuitState(Enum):
    CLOSED = "closed"       # Normal - Anfragen durchlassen
    OPEN = "open"           # Ausgefallen - Anfragen blockieren
    HALF_OPEN = "half_open" # Test - Einzelne Anfragen erlauben
```

#### State Machine

```
                    Erfolg
        ┌──────────────────────────────┐
        │                              │
        ▼                              │
   ┌─────────┐    Fehler > Threshold   │
   │ CLOSED  │────────────────────────▶│
   └─────────┘                         │
        ▲                              │
        │ Erfolg                       │
        │                              ▼
   ┌─────────┐    Timeout          ┌────────┐
   │HALF_OPEN│◀────────────────────│  OPEN  │
   └─────────┘                     └────────┘
        │                              ▲
        │ Fehler                       │
        └──────────────────────────────┘
```

#### Konfiguration

```python
class CircuitBreakerConfig:
    FAILURE_THRESHOLD = 5      # Fehler bis OPEN
    SUCCESS_THRESHOLD = 3      # Erfolge bis CLOSED (aus HALF_OPEN)
    RECOVERY_TIMEOUT = 60      # Sekunden bis HALF_OPEN
    WINDOW_SIZE = 100          # Anfragen für Rate-Berechnung
```

#### Nutzung

```python
from app.services.circuit_breaker import CircuitBreakerRegistry, circuit_breaker_protected

# Registry für alle Backends
registry = CircuitBreakerRegistry()

# Circuit Breaker für Backend holen
breaker = registry.get_breaker("deepseek")

# Manuell prüfen
if breaker.is_available():
    try:
        result = await process_ocr()
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()

# Oder mit Decorator
@circuit_breaker_protected("deepseek")
async def process_with_deepseek(document):
    return await deepseek_agent.process(document)
```

#### Metriken

```python
stats = breaker.get_stats()
# CircuitStats(
#     state=CircuitState.CLOSED,
#     failure_count=2,
#     success_count=150,
#     last_failure=datetime(...),
#     last_success=datetime(...),
#     failure_rate=0.013,
#     is_available=True
# )
```

---

### 4. GPU Memory Guard

**Pfad:** `app/gpu_manager.py`

Der GPU Memory Guard überwacht und erzwingt VRAM-Limits zum Schutz vor OOM-Fehlern.

#### Konfiguration

```python
class GPUMemoryGuard:
    DEFAULT_LIMIT_GB = 13.6    # 85% von 16GB RTX 4080
    WARNING_THRESHOLD = 0.75   # Warnung bei 75%
    CRITICAL_THRESHOLD = 0.90  # Kritisch bei 90%
```

#### Nutzung

```python
from app.gpu_manager import GPUMemoryGuard, gpu_memory_guard

# Guard initialisieren
guard = GPUMemoryGuard(memory_limit_gb=13.6)

# Status prüfen
status = guard.check_memory_status()
# {"allocated_gb": 4.5, "status": "ok", "usage_percent": 33}

# Allocation prüfen
can_alloc = guard.can_allocate(required_gb=8.0)
# {"allowed": True, "remaining_after_gb": 1.1}

# Cache bereinigen
freed = guard.cleanup_cache()
# 1073741824 (1GB in Bytes)

# Als Context Manager
with gpu_memory_guard(required_gb=10.0) as guard:
    result = await model.process(data)
    # Automatisches Cleanup nach Verarbeitung
```

#### Memory Status Levels

| Level | VRAM Nutzung | Aktion |
|-------|-------------|--------|
| `ok` | < 75% | Normal |
| `warning` | 75-90% | Cache bereinigen |
| `critical` | > 90% | Enforcement, kleinere Batches |

---

### 5. OCR Pipeline

**Pfad:** `app/services/ocr_pipeline.py`

Die OCR Pipeline orchestriert alle Komponenten für die Dokumentenverarbeitung.

#### Konfiguration

```python
class OCRPipelineConfig:
    DEFAULT_BACKEND = "deepseek"
    MIN_CONFIDENCE = 0.60
    MAX_RETRIES = 3
    ENABLE_FALLBACK = True
    ENABLE_CIRCUIT_BREAKER = True
```

#### Nutzung

```python
from app.services.ocr_pipeline import OCRPipeline

pipeline = OCRPipeline()

# Einzelnes Dokument verarbeiten
result = await pipeline.process_document(
    document=doc,
    backend="auto",           # Automatische Auswahl
    min_confidence=0.65,
    enable_fallback=True
)
# OCRPipelineResult(
#     success=True,
#     text="Extrahierter Text...",
#     confidence=0.87,
#     backend_used="deepseek",
#     fallbacks_used=[],
#     processing_time_ms=1234
# )

# Batch-Verarbeitung
results = await pipeline.process_batch(
    documents=[doc1, doc2, doc3],
    backend="auto",
    min_confidence=0.60
)

# Pipeline-Status
status = pipeline.get_status()
# {
#     "healthy": True,
#     "backends_available": ["deepseek", "got_ocr"],
#     "circuit_breakers": {...},
#     "confidence_stats": {...}
# }
```

#### Verarbeitungsablauf

```python
async def process_document(document, backend="auto", min_confidence=0.60):
    """
    1. Backend-Auswahl
       - Wenn "auto": Fallback Chain nutzen
       - Sonst: Spezifisches Backend

    2. Circuit Breaker Check
       - Ist Backend verfügbar?
       - Wenn OPEN: Nächstes Backend

    3. GPU Memory Check
       - Genug VRAM verfügbar?
       - Wenn nicht: Kleinere Batch oder CPU-Fallback

    4. OCR Verarbeitung
       - Backend aufrufen
       - Token-Level Confidence extrahieren

    5. Qualitätsprüfung
       - Confidence Level bestimmen
       - Wenn < min_confidence: Fallback

    6. Fallback (wenn nötig)
       - Nächstes Backend versuchen
       - Bis Erfolg oder alle erschöpft

    7. Ergebnis
       - Text, Confidence, Metadaten
       - Metriken für Monitoring
    """
```

---

## Backend-Spezifikationen

### DeepSeek-Janus-Pro

**Pfad:** `app/agents/ocr/deepseek_agent.py`

| Eigenschaft | Wert |
|------------|------|
| VRAM | ~12GB |
| Geschwindigkeit | 2-3 Seiten/s |
| Stärken | Deutsche Texte, Fraktur, komplexe Layouts |
| Schwächen | Hoher Speicherbedarf |

```python
from app.agents.ocr.deepseek_agent import DeepSeekOCRAgent

agent = DeepSeekOCRAgent()
result = await agent.process(
    image=image_bytes,
    options={
        "language": "de",
        "detect_fraktur": True,
        "extract_confidence": True
    }
)
```

### GOT-OCR 2.0

**Pfad:** `app/agents/ocr/got_agent.py`

| Eigenschaft | Wert |
|------------|------|
| VRAM | ~10GB |
| Geschwindigkeit | 5-7 Seiten/s |
| Stärken | Tabellen, Formeln, schnell |
| Schwächen | Fraktur, historische Dokumente |

```python
from app.agents.ocr.got_agent import GOTOCRAgent

agent = GOTOCRAgent()
result = await agent.process(
    image=image_bytes,
    options={
        "extract_tables": True,
        "extract_formulas": True
    }
)
```

### Surya + Docling

**Pfad:** `app/agents/ocr/surya_agent.py`

| Eigenschaft | Wert |
|------------|------|
| VRAM | 0GB (CPU) / 4GB (GPU) |
| Geschwindigkeit | 1-2 Seiten/s |
| Stärken | Layout-Analyse, CPU-Fallback |
| Schwächen | Langsamer, weniger genau |

```python
from app.agents.ocr.surya_agent import SuryaOCRAgent

agent = SuryaOCRAgent(use_gpu=False)  # CPU-Modus
result = await agent.process(
    image=image_bytes,
    options={
        "layout_analysis": True,
        "detect_reading_order": True
    }
)
```

---

## Metriken & Monitoring

### Prometheus Metriken

```python
# OCR Verarbeitung
ocr_processing_total = Counter(
    "ocr_processing_total",
    "Gesamtzahl OCR-Verarbeitungen",
    ["backend", "status"]
)

ocr_processing_duration = Histogram(
    "ocr_processing_duration_seconds",
    "OCR-Verarbeitungsdauer",
    ["backend"],
    buckets=[0.5, 1, 2, 5, 10, 30]
)

# Confidence
ocr_confidence = Histogram(
    "ocr_confidence",
    "OCR Confidence-Verteilung",
    ["backend"],
    buckets=[0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)

# Fallbacks
ocr_fallback_total = Counter(
    "ocr_fallback_total",
    "Fallback-Anzahl",
    ["from_backend", "to_backend", "reason"]
)
```

### Logging

```python
import structlog
logger = structlog.get_logger(__name__)

# Erfolgreiche Verarbeitung
logger.info(
    "ocr_processing_completed",
    document_id=doc_id,
    backend=backend,
    confidence=confidence,
    processing_time_ms=duration,
    fallbacks_used=fallbacks
)

# Fallback
logger.warning(
    "ocr_fallback_triggered",
    document_id=doc_id,
    from_backend=from_backend,
    to_backend=to_backend,
    reason=reason
)

# Fehler
logger.error(
    "ocr_processing_failed",
    document_id=doc_id,
    backend=backend,
    error=str(e),
    fallback_exhausted=True
)
```

---

## Fehlerbehandlung

### Fehlertypen

```python
class OCRPipelineError(Exception):
    """Basis-Exception für Pipeline-Fehler."""

class BackendUnavailableError(OCRPipelineError):
    """Backend temporär nicht verfügbar (Circuit Breaker OPEN)."""

class AllBackendsFailedError(OCRPipelineError):
    """Alle Backends fehlgeschlagen."""

class GPUOutOfMemoryError(OCRPipelineError):
    """GPU-Speicher erschöpft."""

class LowConfidenceError(OCRPipelineError):
    """Confidence unter Schwellwert."""
```

### Recovery-Strategien

| Fehler | Strategie |
|--------|-----------|
| Backend-Fehler | Fallback zu nächstem Backend |
| GPU OOM | Cache leeren, Batch verkleinern, CPU-Fallback |
| Alle Backends ausgefallen | Warteschlange, Retry mit Exponential Backoff |
| Niedrige Confidence | Anderes Backend, manuelle Prüfung |

---

## Best Practices

### 1. Backend-Auswahl

```python
# Für deutsche Dokumente
backend = "deepseek"  # Beste Qualität

# Für Tabellen/Formeln
backend = "got_ocr"  # Schneller, gut strukturiert

# Für Layout-Analyse
backend = "surya"  # Detaillierte Struktur

# Automatische Auswahl
backend = "auto"  # Pipeline entscheidet
```

### 2. Confidence-Handling

```python
# Konservativ (hohe Qualität)
result = await pipeline.process(doc, min_confidence=0.85)

# Standard
result = await pipeline.process(doc, min_confidence=0.60)

# Tolerant (Fallback minimieren)
result = await pipeline.process(doc, min_confidence=0.40)
```

### 3. Batch-Verarbeitung

```python
# Optimale Batch-Größe
batch_size = pipeline.get_optimal_batch_size("deepseek")

# Verarbeitung mit Fortschritt
async for result in pipeline.process_batch_stream(documents):
    print(f"Verarbeitet: {result.document_id}")
```

### 4. Monitoring

```python
# Regelmäßiger Health Check
status = pipeline.get_status()
if not status["healthy"]:
    alert_ops_team(status["problems"])

# Metriken exportieren
metrics = pipeline.export_metrics()
prometheus_push(metrics)
```

---

## Siehe auch

- [Health & Monitoring API](./API/Health_Monitoring_API.md)
- [GPU Performance Baseline](./GPU_Performance_Baseline.md)
- [Troubleshooting Guide](./Guides/Troubleshooting-Guide.md)
- [ML Routing](./ML_ROUTING.md)
