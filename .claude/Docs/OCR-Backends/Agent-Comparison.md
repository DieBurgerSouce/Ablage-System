# OCR Backend Vergleich

Umfassender Vergleich aller OCR-Backends im Ablage-System.

## Uebersicht

| Backend | Modell | VRAM | GPU | Staerken |
|---------|--------|------|-----|----------|
| DeepSeek-Janus-Pro | deepseek-ai/Janus-Pro-1B | 12 GB | Ja | Beste Umlaut-Genauigkeit, Fraktur |
| GOT-OCR 2.0 | stepfun-ai/GOT-OCR2_0 | 10 GB | Nein* | Tabellen, Formeln, schnell |
| OlmOCR-2 | allenai/olmOCR-2-7B-1025 | 14 GB | Ja | Dokument-Verstaendnis, Layouts |
| Qwen2.5-VL-7B | Qwen/Qwen2.5-VL-7B-Instruct | 14 GB | Ja | JSON-Extraktion, Multimodal |
| Surya + Docling | VikParuchuri/surya | 4 GB | Optional | CPU-Fallback, Layout-Analyse |
| PaddleOCR-VL | PaddlePaddle/PaddleOCR-VL | 6 GB | Ja | Schnell, mehrsprachig |

*GOT-OCR 2.0: GPU nicht in aktuellem Setup

## Detaillierte Backend-Beschreibungen

### DeepSeek-Janus-Pro

**Modell**: `deepseek-ai/Janus-Pro-1B`
**VRAM**: ~12 GB
**Typ**: Multimodal Vision-Language Model

**Staerken**:
- Hoechste Genauigkeit bei deutschen Umlauten (ae, oe, ue, ss)
- Exzellente Frakturschrift-Erkennung
- Komplexe Layout-Analyse
- Tabellen-Extraktion

**Schwaеchen**:
- Langsamer als GOT-OCR
- Hoher VRAM-Bedarf

**Verwendung**:
```python
from app.agents.ocr.deepseek_agent import DeepSeekOCRAgent

agent = DeepSeekOCRAgent()
result = await agent.process("document.pdf", language="de")
```

---

### GOT-OCR 2.0

**Modell**: `stepfun-ai/GOT-OCR2_0`
**VRAM**: ~10 GB
**Typ**: Transformer-basierter OCR

**Staerken**:
- Schnellste Verarbeitung
- Hervorragende Tabellen-Erkennung
- Mathematische Formeln
- LaTeX-Output

**Schwaеchen**:
- Probleme mit Frakturschrift
- Gelegentlich Umlaut-Fehler

**Verwendung**:
```python
from app.agents.ocr.got_ocr_agent import GOTOCRAgent

agent = GOTOCRAgent()
result = await agent.process("document.pdf", detect_tables=True)
```

---

### OlmOCR-2 (Allen Institute)

**Modell**: `allenai/olmOCR-2-7B-1025`
**VRAM**: ~14 GB
**Typ**: 7B Vision-Language Model

**Staerken**:
- Tiefes Dokument-Verstaendnis
- Kontextuelle Text-Extraktion
- Multi-Page PDF Verarbeitung
- Strukturierte Daten-Extraktion

**Schwaеchen**:
- Hoechster VRAM-Bedarf
- Langsamste Initialisierung (~60s Model Loading)

**Verwendung**:
```python
from app.agents.ocr.olmocr_agent import OlmOCRAgent

agent = OlmOCRAgent()
result = await agent.process("document.pdf", pages="all")
```

**Thread-Safety**: Verwendet asyncio.Lock fuer Model-Loading

---

### Qwen2.5-VL-7B

**Modell**: `Qwen/Qwen2.5-VL-7B-Instruct`
**VRAM**: ~14 GB
**Typ**: Multimodal Instruct Model

**Staerken**:
- JSON-strukturierte Extraktion
- Custom Prompts
- Multimodal (Bild + Text)
- Gute deutsche Text-Erkennung

**Schwaеchen**:
- Gleicher VRAM wie OlmOCR
- Weniger spezialisiert auf OCR

**Verwendung**:
```python
from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

agent = QwenOCRAgent()
result = await agent.process_with_prompt(
    "invoice.pdf",
    prompt="Extrahiere Rechnungsnummer, Datum, Betrag als JSON"
)
```

---

### Surya + Docling

**Modell**: `VikParuchuri/surya` + `DS4SD/docling`
**VRAM**: ~4 GB (GPU) / 0 GB (CPU)
**Typ**: Layout-aware OCR Pipeline

**Staerken**:
- CPU-Fallback moeglich
- Detaillierte Layout-Analyse
- Niedriger VRAM-Bedarf
- Schnelle GPU-Variante verfuegbar

**Schwaеchen**:
- Niedrigere Genauigkeit als Vision-Language Models
- CPU-Modus langsam

**Verwendung**:
```python
from app.agents.ocr.surya_agent import SuryaOCRAgent

agent = SuryaOCRAgent(use_gpu=True)
result = await agent.process("document.pdf", detect_layout=True)
```

---

### PaddleOCR-VL

**Modell**: `PaddlePaddle/PaddleOCR` + Vision Layer
**VRAM**: ~6 GB
**Typ**: CNN + Transformer OCR

**Staerken**:
- Sehr schnell
- Gute mehrsprachige Unterstuetzung
- Handschrift-Erkennung
- Mobile-optimiert

**Schwaеchen**:
- Weniger genau bei komplexen Layouts
- Paddle-Framework erforderlich

---

## Hybrid Agent

Der `HybridOCRAgent` orchestriert mehrere Backends:

```python
from app.agents.ocr.hybrid_agent import HybridOCRAgent

agent = HybridOCRAgent()
result = await agent.process(
    "document.pdf",
    strategy="best_quality",  # oder "fastest", "consensus"
    backends=["deepseek", "got_ocr", "olmocr"]
)
```

### Strategien

| Strategie | Beschreibung |
|-----------|--------------|
| `best_quality` | Alle Backends, waehlt bestes Ergebnis nach Confidence |
| `fastest` | Schnellstes verfuegbares Backend |
| `consensus` | Character-Level Voting zwischen Backends |
| `fallback` | Kaskade bei Fehler (DeepSeek -> GOT-OCR -> Surya) |

### Character-Level Voting

Bei `consensus` Strategie:
1. Alle Backends extrahieren Text
2. Texte werden Zeichen fuer Zeichen verglichen
3. Mehrheitsentscheidung pro Position
4. DeepSeek erhaelt Bonus bei deutschen Umlauten

```python
# Beispiel: 3 Backends, Position hat "ä", "a", "ä"
# Ergebnis: "ä" (2 von 3 Stimmen)
```

### VRAM-Management

Der Hybrid-Agent verwaltet VRAM dynamisch:
- Parallel bei genug VRAM (>24 GB)
- Sequentiell bei wenig VRAM
- Automatisches GPU Memory Clearing zwischen Backends

## Performance-Vergleich

Getestet auf RTX 4080 (16 GB VRAM):

| Backend | Seiten/Sek | VRAM Peak | Umlaut-Acc. |
|---------|------------|-----------|-------------|
| DeepSeek | 2-3 | 12.5 GB | 99.2% |
| GOT-OCR | 5-7 | 10.2 GB | 96.8% |
| OlmOCR | 1.5-2 | 14.1 GB | 98.5% |
| Qwen2.5 | 2-3 | 13.8 GB | 97.9% |
| Surya GPU | 3-4 | 4.2 GB | 94.5% |
| Surya CPU | 0.5-1 | 0 GB | 94.5% |

## Empfehlungen

| Anwendungsfall | Empfohlenes Backend |
|----------------|---------------------|
| Deutsche Dokumente (Standard) | DeepSeek-Janus-Pro |
| Tabellen/Formulare | GOT-OCR 2.0 |
| Dokument-Verstaendnis | OlmOCR-2 |
| Strukturierte JSON-Extraktion | Qwen2.5-VL |
| Low-VRAM / CPU-Fallback | Surya + Docling |
| Hoechste Qualitaet | HybridAgent (consensus) |
| Schnellste Verarbeitung | GOT-OCR oder Surya GPU |

## Konfiguration

```env
# Backend-Auswahl
OCR_DEFAULT_BACKEND=deepseek
OCR_FALLBACK_CHAIN=deepseek,got_ocr,surya

# VRAM-Management
OCR_MAX_VRAM_PERCENT=85
OCR_PARALLEL_THRESHOLD_GB=24

# Model Loading
OCR_MODEL_TIMEOUT_SECONDS=600
OCR_MODEL_CACHE_ENABLED=true

# Hybrid Agent
OCR_HYBRID_STRATEGY=best_quality
OCR_HYBRID_UMLAUT_BONUS=0.1
```
