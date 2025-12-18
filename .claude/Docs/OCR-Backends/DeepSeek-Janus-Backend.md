# DeepSeek-Janus-Pro OCR Backend

## Übersicht

DeepSeek-Janus-Pro ist ein multimodales Vision-Language-Modell, optimiert für komplexe Dokumentenverarbeitung mit besonderem Fokus auf deutsche Texte.

---

## Technische Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Modell** | `deepseek-ai/Janus-Pro-7B` |
| **Parameter** | 7 Milliarden |
| **VRAM (Vollmodell)** | 24 GB |
| **VRAM (4-bit Quant.)** | 12 GB |
| **Max. Batch Size** | 4 |
| **Timeout** | 600 Sekunden |

---

## Stärken

### 1. Deutsche Umlaut-Genauigkeit

DeepSeek erreicht die höchste Genauigkeit bei deutschen Umlauten:
- ä, ö, ü: > 99% korrekt
- ß: > 98% korrekt
- Historische Schreibweisen (ae → ä)

### 2. Frakturschrift-Erkennung

Speziell trainiert für:
- Fraktur (Blackletter)
- Kurrentschrift
- Historische Dokumente (1800-1945)

### 3. Komplexe Layouts

- Mehrspaltige Dokumente
- Eingebettete Tabellen
- Text-Bild-Kombinationen
- Fußnoten und Marginalien

### 4. Semantisches Verständnis

- Kontext-basierte Korrektur
- Erkennung von Dokumenttypen
- Entity Extraction (Firmen, Personen, Adressen)

---

## Quantisierung

### Optionen für RTX 4080 (16GB)

| Methode | VRAM | Qualitätsverlust | Windows-Support |
|---------|------|------------------|-----------------|
| **GPTQ 4-bit** | ~12 GB | Minimal | ✓ |
| **AWQ 4-bit** | ~11 GB | Minimal | ✓ |
| **BitsAndBytes** | ~12 GB | Minimal | ✗ (Linux only) |

### Aktivierung

```python
# In deepseek_agent.py
ENABLE_QUANTIZATION = True

# GPTQ (bevorzugt auf Windows)
if GPTQ_AVAILABLE:
    model = AutoGPTQForCausalLM.from_quantized(
        MODEL_NAME,
        device="cuda:0",
        use_safetensors=True,
    )

# AWQ (Alternative)
if AWQ_AVAILABLE:
    model = AutoAWQForCausalLM.from_quantized(
        MODEL_NAME,
        device="cuda:0",
    )
```

---

## API-Nutzung

### Standard-Aufruf

```python
from app.agents.ocr.deepseek_agent import DeepSeekAgent

agent = DeepSeekAgent()

result = await agent.process({
    "document_id": "doc-123",
    "image_path": "/path/to/document.png",
    "language": "de",
    "extract_entities": True,
    "detect_fraktur": True,
})
```

### Input-Parameter

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| `document_id` | str | *required* | Dokument-ID |
| `image_path` | str | *required* | Pfad zum Bild |
| `language` | str | `"de"` | Sprache (de, en) |
| `extract_entities` | bool | `False` | NER aktivieren |
| `detect_fraktur` | bool | `False` | Fraktur-Erkennung |
| `quality` | str | `"high"` | Qualitätsstufe |

### Output-Format

```json
{
  "text": "Extrahierter Text mit korrekten Umlauten...",
  "confidence": 0.95,
  "processing_time_ms": 1250,
  "backend": "deepseek-janus",
  "entities": {
    "companies": ["Max Mustermann GmbH"],
    "persons": ["Hans Müller"],
    "addresses": ["Musterstraße 123, 12345 Berlin"],
    "dates": ["15.12.2024"],
    "amounts": ["1.234,56 €"]
  },
  "metadata": {
    "fraktur_detected": false,
    "layout_type": "single_column",
    "page_orientation": "portrait"
  }
}
```

---

## Entity Extraction

### spaCy-Integration

DeepSeek verwendet spaCy für Named Entity Recognition:

```python
# Modell-Priorität
SPACY_MODELS = [
    "de_core_news_lg",  # Beste Qualität
    "de_core_news_md",  # Mittel
    "de_core_news_sm",  # Fallback
]
```

### Installation

```bash
pip install spacy
python -m spacy download de_core_news_lg
```

### Erkannte Entitäten

| Entity | Beispiel |
|--------|----------|
| `PER` | Hans Müller |
| `ORG` | Max Mustermann GmbH |
| `LOC` | Berlin |
| `MISC` | IBAN, Rechnungsnummer |

---

## GPU-Management

### VRAM-Monitoring

```python
# Vor Verarbeitung
current_vram = torch.cuda.memory_allocated() / 1024**3
if current_vram > 12.0:  # 75% des Limits
    torch.cuda.empty_cache()
```

### Race Condition Prevention

```python
# Class-level Lock für Model-Loading
_model_lock: asyncio.Lock = None

async def _load_model(self, device: str):
    async with DeepSeekAgent._model_lock:
        if not self._model_loaded:
            # Model laden...
            self._model_loaded = True
```

---

## Fehlerbehandlung

### GPU Out-of-Memory

```python
try:
    result = await self._run_ocr(image)
except torch.cuda.OutOfMemoryError:
    logger.warning("deepseek_oom", document_id=doc_id)
    await self._handle_gpu_oom()
    # Fallback zu anderem Backend
    raise AgentResourceError("GPU out of memory")
```

### Model Loading Timeout

```python
MODEL_LOADING_TIMEOUT = 600.0  # 10 Minuten

# Erstes Laden kann langsam sein (Model-Download, Quantisierung)
async with asyncio.timeout(MODEL_LOADING_TIMEOUT):
    await self._load_model(device)
```

---

## Performance-Optimierung

### 1. Batch Processing

```python
# Mehrere Bilder gleichzeitig verarbeiten
images = [load_image(p) for p in paths[:MAX_BATCH_SIZE]]
results = await self._run_batch_ocr(images)
```

### 2. spaCy Pre-Loading

```python
# Einmaliges Laden beim Startup
if not DeepSeekAgent._spacy_initialized:
    self._init_spacy_model()  # Spart ~200ms pro Dokument
```

### 3. Quantisierung aktivieren

```python
ENABLE_QUANTIZATION = True  # Reduziert VRAM von 24GB auf 12GB
```

---

## Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `DEEPSEEK_MODEL` | `deepseek-ai/Janus-Pro-7B` | Modell-ID |
| `DEEPSEEK_QUANTIZE` | `true` | Quantisierung aktivieren |
| `DEEPSEEK_MAX_BATCH` | `4` | Max. Batch Size |
| `DEEPSEEK_TIMEOUT` | `600` | Timeout in Sekunden |

### Docker-Konfiguration

```yaml
# docker-compose.yml
worker:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  environment:
    - CUDA_VISIBLE_DEVICES=0
    - DEEPSEEK_QUANTIZE=true
```

---

## Troubleshooting

### Problem: Model lädt nicht

**Ursache**: Fehlende Model-Dateien oder Netzwerk-Timeout
**Lösung**:
```bash
# Model vorab herunterladen
python -c "from transformers import AutoModel; AutoModel.from_pretrained('deepseek-ai/Janus-Pro-7B')"
```

### Problem: CUDA Out of Memory

**Ursache**: Andere Prozesse belegen VRAM
**Lösung**:
```bash
# GPU-Status prüfen
nvidia-smi
# Andere Prozesse beenden oder Batch Size reduzieren
```

### Problem: Umlaute werden falsch erkannt

**Ursache**: Encoding-Problem bei Bildvorverarbeitung
**Lösung**: PIL mit UTF-8 Encoding verwenden

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
