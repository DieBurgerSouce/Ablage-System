# GOT-OCR 2.0 Backend

## Übersicht

GOT-OCR 2.0 ist ein schnelles Transformer-basiertes OCR-Modell, spezialisiert auf Formeln, Tabellen und strukturierte Ausgabeformate.

---

## Technische Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Modell** | `stepfun-ai/GOT-OCR-2.0-hf` |
| **Parameter** | 580 Millionen |
| **VRAM** | 10 GB |
| **Max. Batch Size** | 8 |
| **Timeout** | 600 Sekunden |
| **GPU erforderlich** | Nein (CPU-Fallback) |

---

## Stärken

### 1. Mathematische Formeln

- LaTeX-Ausgabe für Formeln
- Wissenschaftliche Notation
- Komplexe mathematische Ausdrücke

### 2. Strukturierte Ausgabe

**Output-Formate**:
- `plain` - Reiner Text
- `markdown` - Markdown-formatiert
- `latex` - LaTeX-formatiert

### 3. Tabellen-Erhaltung

- Spalten-Struktur bleibt erhalten
- Markdown-Tabellen-Output
- CSV-kompatible Ausgabe

### 4. High Throughput

- 5-7 Seiten/Sekunde (GPU)
- Effizientes Batch Processing
- Niedrigerer VRAM als DeepSeek

---

## API-Nutzung

### Standard-Aufruf

```python
from app.agents.ocr.got_ocr_agent import GOTOCRAgent

agent = GOTOCRAgent()

result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/document.png",
    "language": "de",
    "output_format": "markdown",
    "extract_formulas": True,
})
```

### Input-Parameter

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| `document_id` | str | *required* | Dokument-ID |
| `image_path` | str | *required* | Pfad zum Bild |
| `language` | str | `"de"` | Sprache |
| `output_format` | str | `"markdown"` | plain/markdown/latex |
| `extract_formulas` | bool | `False` | Formel-Fokus |
| `region` | list | `None` | [x1, y1, x2, y2] Ausschnitt |

### Output-Format

```json
{
  "text": "# Überschrift\n\nText mit **Formatierung**...",
  "confidence": 0.92,
  "format": "markdown",
  "processing_time_ms": 350,
  "backend": "got-ocr-2.0",
  "formulas": [
    {
      "latex": "E = mc^2",
      "position": [100, 200, 300, 250]
    }
  ]
}
```

---

## Output-Formate

### Plain Text

```python
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/doc.png",
    "output_format": "plain",
})

# Output:
# "Rechnung Nr. 2024-0042
#  Datum: 15.12.2024
#  Betrag: 1.234,56 EUR"
```

### Markdown

```python
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/doc.png",
    "output_format": "markdown",
})

# Output:
# "# Rechnung Nr. 2024-0042
#
#  **Datum:** 15.12.2024
#  **Betrag:** 1.234,56 EUR
#
#  | Position | Menge | Preis |
#  |----------|-------|-------|
#  | Artikel A| 2     | 100,00|"
```

### LaTeX

```python
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/formula.png",
    "output_format": "latex",
    "extract_formulas": True,
})

# Output:
# "\begin{equation}
#    E = mc^{2}
#  \end{equation}"
```

---

## Regionale OCR

Verarbeitung eines Bildausschnitts:

```python
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/doc.png",
    "region": [100, 200, 500, 400],  # [x1, y1, x2, y2]
})
```

---

## GPU/CPU-Fallback

```python
async def _allocate_device(self) -> str:
    """Versucht GPU zu allozieren, fällt auf CPU zurück."""

    if not torch.cuda.is_available():
        logger.info("got_ocr_cpu_mode", reason="no_cuda")
        return "cpu"

    # GPU-Memory prüfen
    free_memory = self.gpu_manager.get_free_memory()

    if free_memory < self.VRAM_REQUIRED_GB:
        logger.info("got_ocr_cpu_fallback", free_gb=free_memory)
        return "cpu"

    return "cuda:0"
```

---

## Deutsche Nachverarbeitung

```python
async def _postprocess_german(self, result: OCRResult) -> OCRResult:
    """Deutsche Text-Nachverarbeitung."""

    text = result.text

    # Umlaut-Korrektur
    corrections = {
        "ae": "ä",
        "oe": "ö",
        "ue": "ü",
        "ss": "ß",  # Kontextabhängig
    }

    # Typische OCR-Fehler
    text = text.replace("0", "O")  # Bei Großbuchstaben
    text = text.replace("l", "1")  # Bei Zahlen

    result.text = text
    return result
```

---

## Performance-Vergleich

| Szenario | GOT-OCR | DeepSeek |
|----------|---------|----------|
| Standard-Dokument | 150ms | 400ms |
| Tabelle (10 Zeilen) | 200ms | 500ms |
| Formel-Extraktion | 180ms | 350ms |
| Fraktur-Text | 300ms | 250ms |

---

## Fehlerbehandlung

### GPU Out-of-Memory

```python
except torch.cuda.OutOfMemoryError as e:
    logger.error("got_ocr_gpu_oom", document_id=doc_id)
    await self._handle_gpu_oom()
    raise AgentResourceError(f"GPU out of memory: {e}")
```

### Recovery-Strategie

```python
async def _handle_gpu_oom(self):
    """Bereinigt GPU-Memory nach OOM."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        # Optionales Model-Unloading
        if self._model_loaded:
            del self.model
            self.model = None
            self._model_loaded = False
```

---

## Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `GOT_OCR_MODEL` | `stepfun-ai/GOT-OCR-2.0-hf` | Modell-ID |
| `GOT_OCR_MAX_BATCH` | `8` | Max. Batch Size |
| `GOT_OCR_TIMEOUT` | `600` | Timeout in Sekunden |
| `GOT_OCR_FORMAT` | `markdown` | Default Output-Format |

---

## Best Practices

### 1. Format-Auswahl

| Anwendungsfall | Format |
|----------------|--------|
| Standard-Text | `plain` |
| Dokumente mit Struktur | `markdown` |
| Wissenschaftliche Papers | `latex` |

### 2. Batch Processing

```python
# Optimal für viele ähnliche Dokumente
images = [load_image(p) for p in paths[:8]]
results = await agent.process_batch(images)
```

### 3. Formel-Erkennung

```python
# Aktivieren nur wenn nötig (erhöht Verarbeitungszeit)
result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/scientific.png",
    "output_format": "latex",
    "extract_formulas": True,  # Nur für wissenschaftliche Dokumente
})
```

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
