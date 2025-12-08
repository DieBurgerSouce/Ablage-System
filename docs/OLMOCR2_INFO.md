# OlmOCR-2 - Modell-Information

**Stand:** 08. Dezember 2025
**Entwickler:** Allen Institute for AI (Ai2)
**Release:** Oktober 2025

---

## Ubersicht

OlmOCR-2 ist ein vollstandig offenes OCR-Modell von Allen AI, das State-of-the-Art Performance erreicht. Es basiert auf Qwen2.5-VL und wurde speziell fur Dokumenten-OCR trainiert.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **Parameter** | 7B |
| **Basis-Modell** | Qwen2.5-VL-7B-Instruct |
| **VRAM** | ~14GB (FP16) / ~7GB (FP8) |
| **Training Data** | olmOCR-mix-1025 (270.000 PDF-Seiten) |
| **Output-Formate** | Markdown, HTML (Tabellen), LaTeX (Mathe) |

---

## Benchmark-Ergebnisse (olmOCR-Bench)

| Modell | Score |
|--------|-------|
| Chandra (9B) | 83.1 ± 0.9 |
| **OlmOCR-2 (7B)** | **82.4 ± 1.1** |
| dots.ocr | 79.1 |
| olmOCR (v1) | 78.5 |
| DeepSeek OCR | 75.4 |

---

## Besondere Eigenschaften

### GRPO RL Training

OlmOCR-2 wurde zusatzlich mit Reinforcement Learning (GRPO) trainiert fur:
- **Mathematische Gleichungen** - LaTeX-Ausgabe
- **Tabellen** - HTML-Ausgabe
- **Komplexe OCR-Falle** - Handschrift, alte Scans

### FP8 Quantisierung

- **3.400 Output Tokens/Sekunde** auf H100
- **10.000 Seiten fur < $2** Rechenkosten
- Effiziente Inferenz fur Massenverarbeitung

### Training-Daten

olmOCR-mix-1025 enthalt:
- Akademische Paper
- Historische Scans
- Rechtsdokumente
- Broschuren
- Diverse Layouts

---

## Architektur

```
┌─────────────────────────────────────┐
│         Eingabe: Seiten-Bild        │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│        Vision Encoder               │
│   (Verarbeitet das Bild)            │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│        Text Decoder                 │
│   (Generiert strukturierten Text)   │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│            Output                   │
│  - Markdown (Uberschriften/Struktur)│
│  - HTML (Tabellen)                  │
│  - LaTeX (Mathematik)               │
└─────────────────────────────────────┘
```

---

## Installation

```bash
pip install olmocr
```

Oder via Hugging Face:
```python
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

model = Qwen2VLForConditionalGeneration.from_pretrained(
    "allenai/olmOCR-2-7B-1025",
    torch_dtype=torch.float16,
    device_map="cuda"
)
processor = AutoProcessor.from_pretrained("allenai/olmOCR-2-7B-1025")
```

---

## Beispiel-Code

```python
from olmocr import OlmOCR

# Modell laden
ocr = OlmOCR()

# PDF verarbeiten
result = ocr.process("document.pdf")

# Strukturierter Output
print(result.markdown)  # Markdown mit Struktur
print(result.tables)    # Tabellen als HTML
print(result.equations) # Gleichungen als LaTeX
```

---

## Links

- **GitHub:** https://github.com/allenai/olmocr
- **Hugging Face:** https://huggingface.co/allenai/olmOCR-2-7B-1025
- **Allen AI Blog:** https://allenai.org/blog/olmocr-2
- **Paper:** arXiv (verfugbar)

---

## Vergleich: OlmOCR-2 vs Chandra vs Surya

| Kriterium | OlmOCR-2 | Chandra | Surya GPU |
|-----------|----------|---------|-----------|
| **Parameter** | 7B | 9B | ~250M |
| **Benchmark** | 82.4 | 83.1 | N/A |
| **VRAM** | ~14GB | ~16GB | 2.5GB |
| **Architektur** | VLM | VLM | Pipeline |
| **Geschwindigkeit** | Mittel | Mittel | Schnell |
| **Vollstandig offen** | **Ja** | Ja | Ja |

---

## Empfehlung fur unser System

| Aspekt | Bewertung |
|--------|-----------|
| **Testen?** | **JA** |
| **Prioritat** | Nach Chandra |
| **VRAM-Kompatibilitat** | Gut (14GB, FP8 moglich) |
| **Vorteile** | Kleiner als Chandra, FP8-Quantisierung |

### Warum OlmOCR-2 interessant ist

1. **Kleiner als Chandra** (7B vs 9B)
2. **FP8-Quantisierung** verfugbar = weniger VRAM
3. **Vollstandig offen** - Daten, Code, Modell
4. **Nah an Chandra-Performance** (82.4 vs 83.1)

### Wann OlmOCR-2 statt Chandra?

- Wenn Chandra zu viel VRAM braucht
- Wenn schnellere Inferenz gebraucht wird
- Als Backup-Option

**Nachster Schritt:** Nach Chandra-Tests OlmOCR-2 evaluieren, falls Chandra VRAM-Probleme hat.
