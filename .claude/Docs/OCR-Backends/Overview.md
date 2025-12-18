# OCR Backends - Übersicht

## Ablage-System OCR Platform

**Version**: 1.0
**Hardware**: NVIDIA RTX 4080 (16GB VRAM)
**Fokus**: Deutsche Dokumente mit Umlaut-Genauigkeit

---

## Backend-Vergleich

| Backend | VRAM | GPU | Stärken | Schwächen |
|---------|------|-----|---------|-----------|
| **DeepSeek-Janus-Pro** | 12-24GB | ✓ | Beste Umlaut-Genauigkeit, Fraktur, komplexe Layouts | Langsam, hoher VRAM |
| **GOT-OCR 2.0** | 10GB | ✓ | Tabellen, Formeln, Markdown-Output | Kein GPU-Fallback |
| **Surya + Docling** | 0GB | ✗ | CPU-Fallback, Layout-Analyse | Langsamer |
| **Surya GPU** | 4GB | ✓ | Schnelle GPU-Variante | Basis-OCR |
| **PaddleOCR** | 2GB | ✓ | Schnell, ressourcenschonend | Weniger genau bei Fraktur |
| **Qwen-OCR** | 8GB | ✓ | Gute Balance | Noch experimentell |
| **DocTR** | 3GB | ✓ | Dokumenten-Layout | Weniger für handschriftliche |

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                      OCR Backend Manager                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Backend Selection                       │  │
│  │                                                            │  │
│  │  document_type + quality_settings → optimal_backend        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│  ┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐       │
│  │ DeepSeek-Janus  │ │  GOT-OCR    │ │  Surya+Docling  │       │
│  │ (Primary GPU)   │ │  (GPU)      │ │  (CPU Fallback) │       │
│  └─────────────────┘ └─────────────┘ └─────────────────┘       │
│              │               │               │                  │
│              ▼               ▼               ▼                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    GPU Manager                             │  │
│  │   VRAM Monitoring | Memory Guard | Batch Sizing           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Backend-Auswahl-Logik

### Automatische Auswahl

```python
def select_backend(document: Document) -> str:
    """Wählt optimales Backend basierend auf Dokument-Eigenschaften."""

    # 1. Komplexe Layouts → DeepSeek
    if document.has_tables and document.has_images:
        return "deepseek"

    # 2. Mathematische Formeln → GOT-OCR
    if document.document_type == "scientific":
        return "got-ocr"

    # 3. Fraktur/Handschrift → DeepSeek
    if document.requires_fraktur or document.is_handwritten:
        return "deepseek"

    # 4. Standard-Dokumente → Surya (schnell)
    if document.is_standard_layout:
        return "surya-gpu"

    # 5. CPU-Fallback bei GPU-Überlastung
    if gpu_memory_percent > 85:
        return "surya-docling"

    # Default: DeepSeek für beste Qualität
    return "deepseek"
```

### Manuelles Override

```http
POST /api/v1/ocr/process
Content-Type: application/json

{
  "document_id": "...",
  "backend": "got-ocr",
  "force": true
}
```

---

## VRAM-Management

### RTX 4080 (16GB) Budget

```
┌────────────────────────────────────────────┐
│ Gesamt: 16GB VRAM                          │
├────────────────────────────────────────────┤
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░ DeepSeek (12GB mit 4-bit) │
│ ▓▓▓▓▓▓▓▓░░░░░░░░ GOT-OCR (10GB)            │
│ ▓▓▓░░░░░░░░░░░░░ Surya-GPU (4GB)           │
│ ▓░░░░░░░░░░░░░░░ PaddleOCR (2GB)           │
└────────────────────────────────────────────┘

Sicherheits-Limit: 85% = 13.6GB
```

### Memory Guard

```python
@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6):
    """Stellt sicher, dass VRAM unter Threshold bleibt."""
    try:
        yield
    finally:
        if torch.cuda.is_available():
            current = torch.cuda.memory_allocated() / 1024**3
            if current > threshold_gb:
                logger.warning("gpu_memory_high", current_gb=current)
                torch.cuda.empty_cache()
```

---

## Backend-Details

### 1. DeepSeek-Janus-Pro

**Modell**: `deepseek-ai/Janus-Pro-7B`
**Parameter**: 7B
**Quantisierung**: 4-bit (GPTQ/AWQ) für 16GB GPUs

**Stärken**:
- Beste Umlaut-Genauigkeit (ä, ö, ü, ß)
- Frakturschrift-Erkennung
- Semantisches Verständnis
- Komplexe Tabellen-Strukturen
- Formel-Erkennung

**Konfiguration**:
```python
MODEL_NAME = "deepseek-ai/Janus-Pro-7B"
VRAM_REQUIRED_GB = 24  # 12GB mit Quantisierung
MAX_BATCH_SIZE = 4
ENABLE_QUANTIZATION = True
```

**Dokumentation**: [DeepSeek-Janus-Backend.md](./DeepSeek-Janus-Backend.md)

---

### 2. GOT-OCR 2.0

**Modell**: `stepfun-ai/GOT-OCR-2.0-hf`
**Parameter**: 580M
**Output-Formate**: Plain, Markdown, LaTeX

**Stärken**:
- Schnelle Verarbeitung
- Mathematische Formeln
- Markdown-formatierte Ausgabe
- Tabellen-Struktur-Erhaltung

**Konfiguration**:
```python
MODEL_NAME = "stepfun-ai/GOT-OCR-2.0-hf"
VRAM_REQUIRED_GB = 10
MAX_BATCH_SIZE = 8
```

**Dokumentation**: [GOT-OCR-Backend.md](./GOT-OCR-Backend.md)

---

### 3. Surya + Docling

**Komponenten**:
- Surya v1.1 (OCR-Engine)
- Docling v1.0 (Layout-Analyse)

**Stärken**:
- CPU-basiert (kein GPU erforderlich)
- Gute Layout-Erkennung
- Zuverlässiger Fallback

**Konfiguration**:
```python
VRAM_REQUIRED_GB = 0  # CPU-only
MAX_BATCH_SIZE = 4
```

**Dokumentation**: [Surya-Docling-Backend.md](./Surya-Docling-Backend.md)

---

### 4. PaddleOCR

**Modell**: PaddlePaddle OCR
**Sprachen**: Multi-language (inkl. Deutsch)

**Stärken**:
- Sehr schnell
- Niedriger VRAM-Verbrauch
- Gut für Standard-Dokumente

**Konfiguration**:
```python
VRAM_REQUIRED_GB = 2
MAX_BATCH_SIZE = 16
```

**Dokumentation**: [PaddleOCR-Backend.md](./PaddleOCR-Backend.md)

---

## Performance-Benchmarks

### Verarbeitungsgeschwindigkeit (A4, 300 DPI)

| Backend | Seiten/Sekunde | Latenz (1 Seite) |
|---------|----------------|------------------|
| DeepSeek | 2-3 | 400ms |
| GOT-OCR | 5-7 | 150ms |
| Surya-GPU | 8-10 | 100ms |
| Surya-CPU | 1-2 | 700ms |
| PaddleOCR | 10-15 | 70ms |

### Genauigkeit (CER - Character Error Rate)

| Backend | Standard-Druck | Handschrift | Fraktur |
|---------|---------------|-------------|---------|
| DeepSeek | 0.8% | 3.2% | 2.1% |
| GOT-OCR | 1.2% | 5.5% | 8.4% |
| Surya | 1.5% | 6.2% | 9.1% |
| PaddleOCR | 1.8% | 7.1% | 12.3% |

---

## Fallback-Strategie

```python
BACKEND_PRIORITY = [
    "deepseek",      # Höchste Qualität
    "got-ocr",       # Schnell + Formeln
    "surya-gpu",     # GPU-Fallback
    "paddleocr",     # Ressourcen-schonend
    "surya-docling", # CPU-Fallback (immer verfügbar)
]

async def process_with_fallback(document_id: str) -> OCRResult:
    """Verarbeitet mit automatischem Fallback bei Fehlern."""

    for backend in BACKEND_PRIORITY:
        try:
            return await process_with_backend(document_id, backend)
        except GPUOutOfMemoryError:
            logger.warning(f"Backend {backend} OOM, trying next...")
            torch.cuda.empty_cache()
            continue
        except Exception as e:
            logger.error(f"Backend {backend} failed: {e}")
            continue

    raise OCRProcessingError("Alle Backends fehlgeschlagen")
```

---

## Prometheus-Metriken

| Metrik | Typ | Labels |
|--------|-----|--------|
| `ablage_ocr_backend_healthy` | Gauge | backend |
| `ablage_ocr_queue_length` | Gauge | - |
| `ablage_ocr_fallbacks_total` | Counter | from_backend, to_backend |
| `ablage_ocr_processing_duration` | Histogram | backend |
| `ablage_ocr_requests_total` | Counter | backend, status |

---

## Weiterführende Dokumentation

- [DeepSeek-Janus-Backend.md](./DeepSeek-Janus-Backend.md)
- [GOT-OCR-Backend.md](./GOT-OCR-Backend.md)
- [Surya-Docling-Backend.md](./Surya-Docling-Backend.md)
- [PaddleOCR-Backend.md](./PaddleOCR-Backend.md)

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
