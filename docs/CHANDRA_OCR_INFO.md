# Chandra OCR - Modell-Information

**Stand:** 08. Dezember 2025
**Entwickler:** Datalab (gleiche wie Surya/Marker)
**Release:** Oktober 2025

---

## Ubersicht

Chandra ist das neueste OCR-Modell von Datalab, den Machern von Surya und Marker. Es wurde entwickelt, um die Limitierungen von Pipeline-basierten OCR-Ansatzen zu uberwinden.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **Parameter** | 9B |
| **Basis-Modell** | Qwen-3-VL (Vision-Language Model) |
| **VRAM** | ~14-16GB |
| **Sprachen** | 40+ (inkl. Deutsch) |
| **Output-Formate** | HTML, Markdown, JSON |

---

## Benchmark-Ergebnisse (olmOCR-Bench)

| Modell | Score | Ranking |
|--------|-------|---------|
| **Chandra (9B)** | **83.1 ± 0.9** | **#1** |
| OlmOCR-2 (7B) | 82.3 ± 1.1 | #2 |
| dots.ocr | 79.1 | #3 |
| olmOCR | 78.5 | #4 |
| DeepSeek OCR | 75.4 ± 1.0 | #5 |
| GPT-4o | < 83.1 | - |
| Gemini Flash 2 | < 83.1 | - |

---

## Spezifische Starken

| Kategorie | Score |
|-----------|-------|
| **Tabellen-Erkennung** | 88.0% |
| **Tiny Text** | 92.3% |
| **Mathematische Notation** | 80.3% |
| **Handschrift** | Sehr gut |
| **Formulare (Checkboxes)** | Sehr gut |
| **Multi-Column Layouts** | Sehr gut |

---

## Warum Chandra fur unser System interessant ist

### Vorteile

1. **Vom gleichen Team wie Surya**
   - Datalab kennt die Schwachen von Surya
   - Chandra wurde gezielt fur diese Lucken entwickelt

2. **Beste Benchmark-Performance**
   - Schlagt alle Open-Source Modelle
   - Schlagt sogar GPT-4o und Gemini

3. **Strukturierte Outputs**
   - HTML fur Tabellen
   - Markdown fur Dokument-Struktur
   - JSON fur maschinelle Verarbeitung

4. **Layout-Erhaltung**
   - Behalt Dokument-Layout bei
   - Wichtig fur Rechnungen mit komplexen Layouts

### Risiken

1. **VRAM-Verbrauch**
   - ~14-16GB (RTX 4080 hat 16GB)
   - Wenig Spielraum fur andere Modelle

2. **Ungetestet mit deutschen IBANs**
   - Muss noch mit unseren Testdokumenten gepruft werden

3. **Langsamer als Surya**
   - VLM-basiert = mehr Rechenaufwand
   - Geschatzt: 20-40s pro Dokument

---

## Installation

```bash
pip install chandra-ocr
```

Oder via Hugging Face:
```python
from transformers import AutoModel, AutoProcessor

model = AutoModel.from_pretrained("datalab-to/chandra")
processor = AutoProcessor.from_pretrained("datalab-to/chandra")
```

---

## Beispiel-Code

```python
from chandra import Chandra

# Modell laden
ocr = Chandra()

# Bild verarbeiten
result = ocr.process("invoice.tif")

# Output als Markdown
print(result.markdown)

# Output als JSON (strukturiert)
print(result.json)
```

---

## Links

- **GitHub:** https://github.com/datalab-to/chandra
- **Hugging Face:** https://huggingface.co/datalab-to/chandra
- **Datalab Blog:** https://www.datalab.to/blog/introducing-chandra

---

## Empfehlung fur unser System

| Aspekt | Bewertung |
|--------|-----------|
| **Testen?** | **JA - Hochste Prioritat** |
| **Als Ersatz fur Surya?** | Moglicherweise |
| **VRAM-Kompatibilitat** | Grenzwertig (14-16GB) |
| **Erwartete IBAN-Genauigkeit** | Unbekannt - muss getestet werden |

**Nachster Schritt:** Chandra auf den gleichen 10 Testdokumenten testen und IBAN-Genauigkeit mit Surya vergleichen.
