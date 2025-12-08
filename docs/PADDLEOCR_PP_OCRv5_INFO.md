# PaddleOCR PP-OCRv5 - CPU OCR Alternative

**Stand:** 08. Dezember 2025
**Entwickler:** Baidu (PaddlePaddle Team)
**Release:** Mai 2025

---

## Ubersicht

PaddleOCR PP-OCRv5 ist ein leichtgewichtiges, CPU-optimiertes OCR-System von Baidu. Es ist speziell fur ressourceneffiziente Verarbeitung auf CPU ausgelegt.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **GPU erforderlich** | **NEIN - CPU-optimiert** |
| **RAM** | ~2GB |
| **Sprachen** | 106 (inkl. Deutsch) |
| **Modellgrosse** | ~10MB (Server) / ~3MB (Mobile) |
| **Architektur** | Pipeline (Detection + Recognition) |

---

## Performance-Verbesserungen gegenuber v4

| Kategorie | Verbesserung |
|-----------|--------------|
| **Allgemeine Genauigkeit** | +13% |
| **Mehrsprachig** | +30% |
| **Vertikaler Text** | Signifikant besser |
| **Handschrift** | Signifikant besser |
| **Seltene Zeichen** | Signifikant besser |

---

## Benchmark-Ergebnisse

| Modell-Variante | Genauigkeit |
|-----------------|-------------|
| PP-OCRv5 Server | **86.38%** |
| PP-OCRv5 Mobile | ~80% |
| PP-OCRv4 | ~75% |
| Tesseract | ~60-70% |

---

## Starken fur unser System

### Vorteile

1. **Kein GPU erforderlich**
   - Lauft vollstandig auf CPU
   - Ideal als Fallback wenn GPU belegt

2. **106 Sprachen**
   - Deutsch vollstandig unterstutzt
   - Einzelnes Modell fur alle Sprachen

3. **Ressourceneffizient**
   - ~2GB RAM
   - Kleine Modellgrosse
   - Schnelle Inferenz auf CPU

4. **Offline-fahig**
   - Keine Cloud-Anbindung
   - Datenschutz-konform
   - Ideal fur sensible Dokumente (Rechnungen, IBANs)

5. **Aktiv gepflegt**
   - Baidu-Support
   - Grosse Community
   - Regelmasige Updates

### Risiken

1. **IBAN-Genauigkeit ungetestet**
   - Muss mit unseren Dokumenten getestet werden

2. **Keine strukturierten Outputs**
   - Nur Text + Bounding Boxes
   - Kein Markdown/HTML/JSON

---

## Installation

```bash
pip install paddlepaddle paddleocr
```

Oder mit GPU-Support (optional):
```bash
pip install paddlepaddle-gpu paddleocr
```

---

## Beispiel-Code

```python
from paddleocr import PaddleOCR

# CPU-Modus (Standard)
ocr = PaddleOCR(
    use_angle_cls=True,
    lang='german',
    use_gpu=False  # Explizit CPU
)

# Bild verarbeiten
result = ocr.ocr('invoice.tif', cls=True)

# Ergebnisse ausgeben
for line in result[0]:
    bbox = line[0]
    text = line[1][0]
    confidence = line[1][1]
    print(f'{text} (Conf: {confidence:.2f})')
```

---

## Vergleich: PaddleOCR vs Surya CPU

| Kriterium | PaddleOCR v5 | Surya CPU |
|-----------|--------------|-----------|
| **GPU** | Nein | Nein |
| **RAM** | ~2GB | ~4GB |
| **Sprachen** | 106 | 90+ |
| **Modellgrosse** | ~10MB | ~250MB |
| **Benchmark** | 86.38% | ~85% |
| **Community** | Sehr gross | Gross |
| **Struktur-Output** | Nein | Ja (Layout) |

---

## Links

- **GitHub:** https://github.com/PaddlePaddle/PaddleOCR
- **Dokumentation:** https://paddlepaddle.github.io/PaddleOCR
- **PyPI:** https://pypi.org/project/paddleocr/

---

## Empfehlung fur unser System

| Aspekt | Bewertung |
|--------|-----------|
| **Testen?** | **JA** |
| **Als CPU-Fallback** | Sehr gut geeignet |
| **Prioritat** | Hoch (beste CPU-Option) |

### Warum PaddleOCR als CPU-Alternative?

1. **Beste CPU-Performance** unter Open-Source OCR
2. **106 Sprachen** mit einem Modell
3. **Sehr ressourceneffizient** (~2GB RAM)
4. **Aktiv gepflegt** von Baidu

### Einsatz-Szenario

```
GPU verfugbar?
  -> JA: Surya GPU (2.5GB VRAM, schnell)
  -> NEIN: PaddleOCR PP-OCRv5 (CPU, effizient)
```

**Nachster Schritt:** PaddleOCR auf den gleichen 10 Testdokumenten testen und IBAN-Genauigkeit mit Surya CPU vergleichen.
