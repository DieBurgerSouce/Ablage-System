# Surya + Docling Backend

## Übersicht

Die Kombination aus Surya (OCR-Engine) und Docling (Layout-Analyse) bietet einen zuverlässigen CPU-basierten Fallback für GPU-Ausfälle oder Überlastung.

---

## Architektur

```
┌─────────────────────────────────────────────────┐
│                 Input: Dokument                 │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│              Docling Layout-Analyse             │
│                                                 │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐    │
│  │  Tabellen │ │  Bilder   │ │  Text-    │    │
│  │  erkennen │ │  erkennen │ │  blöcke   │    │
│  └───────────┘ └───────────┘ └───────────┘    │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│                Surya OCR Engine                 │
│                                                 │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐    │
│  │ Text-     │ │ Layout-   │ │ Reading   │    │
│  │ Detection │ │ Ordering  │ │ Order     │    │
│  └───────────┘ └───────────┘ └───────────┘    │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│               Strukturierter Output             │
└─────────────────────────────────────────────────┘
```

---

## Technische Spezifikationen

### Surya

| Eigenschaft | Wert |
|-------------|------|
| **Version** | v1.1 |
| **VRAM** | 0 GB (CPU) / 4 GB (GPU) |
| **Sprachen** | 90+ (inkl. Deutsch) |
| **Batch Size** | 4 (CPU) / 16 (GPU) |

### Docling

| Eigenschaft | Wert |
|-------------|------|
| **Version** | v1.0 |
| **VRAM** | 0 GB |
| **Layout-Typen** | Tabellen, Listen, Überschriften |
| **Output** | JSON, Markdown |

---

## Varianten

### 1. Surya + Docling (CPU)

**Datei**: `surya_docling_agent.py`

```python
VRAM_REQUIRED_GB = 0  # CPU-only
MAX_BATCH_SIZE = 4
```

**Verwendung**: Standard-Fallback bei GPU-Problemen

### 2. Surya GPU

**Datei**: `surya_gpu_agent.py`

```python
VRAM_REQUIRED_GB = 4
MAX_BATCH_SIZE = 16
```

**Verwendung**: Schnelle GPU-Verarbeitung bei niedrigem VRAM

### 3. Surya + Docling Enhanced

**Datei**: `surya_docling_enhanced_agent.py`

```python
# Erweitert mit zusätzlichen Features:
# - Verbesserte Tabellen-Erkennung
# - Multi-Column Layout Support
# - Reading Order Detection
```

---

## API-Nutzung

### Standard-Aufruf

```python
from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent

agent = SuryaDoclingAgent()

result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/document.png",
    "language": "de",
    "analyze_layout": True,
    "extract_tables": True,
})
```

### Input-Parameter

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| `document_id` | str | *required* | Dokument-ID |
| `image_path` | str | *required* | Pfad zum Bild |
| `language` | str | `"de"` | Sprache |
| `analyze_layout` | bool | `True` | Layout-Analyse aktivieren |
| `extract_tables` | bool | `False` | Tabellen extrahieren |
| `detect_reading_order` | bool | `True` | Lesereihenfolge erkennen |

### Output-Format

```json
{
  "text": "Extrahierter Text in Lesereihenfolge...",
  "confidence": 0.88,
  "processing_time_ms": 850,
  "backend": "surya-docling",
  "layout": {
    "type": "multi_column",
    "columns": 2,
    "elements": [
      {
        "type": "heading",
        "text": "Überschrift",
        "bbox": [50, 100, 500, 130],
        "level": 1
      },
      {
        "type": "paragraph",
        "text": "Textabschnitt...",
        "bbox": [50, 150, 400, 300]
      },
      {
        "type": "table",
        "rows": 5,
        "cols": 3,
        "bbox": [50, 320, 500, 500]
      }
    ]
  },
  "tables": [
    {
      "id": 0,
      "markdown": "| Header | Col2 |\n|--------|------|\n| Data   | Data |",
      "cells": [...]
    }
  ]
}
```

---

## Layout-Analyse (Docling)

### Erkannte Element-Typen

| Typ | Beschreibung |
|-----|--------------|
| `heading` | Überschriften (Level 1-6) |
| `paragraph` | Textabschnitte |
| `table` | Tabellen |
| `list` | Aufzählungen/Nummerierungen |
| `figure` | Bilder/Diagramme |
| `caption` | Bild-/Tabellenbeschriftungen |
| `footer` | Fußzeilen |
| `header` | Kopfzeilen |

### Multi-Column Detection

```python
layout = docling.analyze_layout(image)

if layout.column_count > 1:
    # Lesereihenfolge über Spalten
    text = docling.extract_with_reading_order(image, layout)
else:
    # Einfache Top-to-Bottom Extraktion
    text = surya.extract_text(image)
```

---

## Tabellen-Extraktion

### Markdown-Output

```python
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/table.png",
    "extract_tables": True,
})

# result["tables"][0]["markdown"]:
# | Produkt | Menge | Preis |
# |---------|-------|-------|
# | A       | 10    | 99,00 |
# | B       | 5     | 49,50 |
```

### Strukturierte Daten

```python
table = result["tables"][0]

# Zugriff auf Zellen
for row in table["cells"]:
    for cell in row:
        print(f"{cell['text']} at ({cell['row']}, {cell['col']})")
```

---

## Performance-Optimierung

### 1. Batch Processing (GPU-Variante)

```python
# surya_gpu_agent.py
images = [load_image(p) for p in paths[:16]]
results = await agent.process_batch(images)
```

### 2. Layout-Caching

```python
# Wenn gleiches Layout für mehrere Seiten
layout_cache = {}

for page in document.pages:
    if page.layout_hash in layout_cache:
        layout = layout_cache[page.layout_hash]
    else:
        layout = docling.analyze_layout(page.image)
        layout_cache[page.layout_hash] = layout
```

### 3. Selektive Analyse

```python
# Nur Text extrahieren (schneller)
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/doc.png",
    "analyze_layout": False,  # Spart ~30% Zeit
    "extract_tables": False,
})
```

---

## CPU vs GPU Vergleich

| Metrik | CPU (Surya+Docling) | GPU (Surya) |
|--------|---------------------|-------------|
| VRAM | 0 GB | 4 GB |
| Seiten/Sekunde | 1-2 | 8-10 |
| Latenz (1 Seite) | 700ms | 100ms |
| Batch Size | 4 | 16 |
| Verfügbarkeit | Immer | Bei freier GPU |

---

## Fehlerbehandlung

### Fallback-Chain

```python
async def process_with_fallback(doc_id: str) -> OCRResult:
    """Surya als letzter Fallback."""

    # 1. Primäre GPU-Backends versuchen
    for backend in ["deepseek", "got-ocr", "surya-gpu"]:
        try:
            return await process_with_backend(doc_id, backend)
        except GPUOutOfMemoryError:
            continue

    # 2. CPU-Fallback (immer verfügbar)
    return await surya_docling_agent.process({
        "document_id": doc_id,
        "image_path": get_image_path(doc_id),
    })
```

### Timeout-Handling

```python
# CPU kann bei großen Dokumenten langsam sein
async with asyncio.timeout(300):  # 5 Minuten
    result = await agent.process(input_data)
```

---

## Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `SURYA_USE_GPU` | `false` | GPU-Modus aktivieren |
| `SURYA_MAX_BATCH` | `4` | Max. Batch Size (CPU) |
| `SURYA_TIMEOUT` | `300` | Timeout in Sekunden |
| `DOCLING_TABLES` | `true` | Tabellen-Erkennung |

---

## Einschränkungen

### Bekannte Limitierungen

1. **Fraktur-Schrift**: Geringere Genauigkeit als DeepSeek
2. **Handschrift**: Nur eingeschränkte Unterstützung
3. **Komplexe Formeln**: Kein LaTeX-Output
4. **Geschwindigkeit**: Langsamer als GPU-Backends

### Empfohlene Verwendung

| Szenario | Empfehlung |
|----------|------------|
| Standard-Dokumente | ✓ Gut geeignet |
| Tabellen | ✓ Gut geeignet |
| Fraktur | ✗ DeepSeek verwenden |
| Formeln | ✗ GOT-OCR verwenden |
| GPU nicht verfügbar | ✓ Einzige Option |

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
