# docTR - CPU OCR Alternative mit deutschem Modell

**Stand:** 08. Dezember 2025
**Entwickler:** Mindee
**Release:** Kontinuierliche Updates

---

## Ubersicht

docTR (Document Text Recognition) ist eine Open-Source OCR-Bibliothek von Mindee, speziell optimiert fur Dokumentenverarbeitung. Sie bietet ein **deutsches Modell** und lauft effizient auf CPU.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **GPU erforderlich** | **NEIN - CPU-optimiert** |
| **RAM** | ~1GB |
| **Deutsche Modell** | **JA** (db_resnet50 + crnn_vgg16_bn) |
| **Architektur** | Two-Stage (Detection + Recognition) |
| **Framework** | PyTorch oder TensorFlow |

---

## Verfugbare Modelle

### Detection (Texterkennung)
| Modell | Grosse | Genauigkeit |
|--------|--------|-------------|
| db_resnet50 | ~100MB | Hoch |
| db_mobilenet_v3 | ~20MB | Mittel |
| linknet_resnet18 | ~50MB | Mittel-Hoch |

### Recognition (Zeichenerkennung)
| Modell | Grosse | Sprache |
|--------|--------|---------|
| crnn_vgg16_bn | ~60MB | Mehrsprachig |
| crnn_mobilenet_v3 | ~10MB | Mehrsprachig |
| **german** | ~60MB | **Deutsch** |

---

## Starken fur unser System

### Vorteile

1. **Deutsches Modell verfugbar**
   - Speziell fur deutsche Dokumente trainiert
   - Bessere Umlaut-Erkennung (a, o, u, ss)

2. **Kein GPU erforderlich**
   - Vollstandige CPU-Unterstutzung
   - Auch GPU-Beschleunigung moglich

3. **Sehr leichtgewichtig**
   - ~1GB RAM
   - Kleine Modelle verfugbar

4. **Gute Dokumentation**
   - Aktive Community
   - Mindee-Support

5. **Einfache Integration**
   - Klare API
   - PyTorch/TensorFlow Support

### Risiken

1. **Weniger Sprachen als PaddleOCR**
   - Fokus auf europaische Sprachen

2. **Kleinere Community**
   - Weniger Ressourcen als PaddleOCR

---

## Installation

```bash
# Mit PyTorch Backend (empfohlen)
pip install "python-doctr[torch]"

# Oder mit TensorFlow Backend
pip install "python-doctr[tf]"
```

---

## Beispiel-Code

```python
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

# Deutsches Modell laden (CPU)
model = ocr_predictor(
    det_arch='db_resnet50',
    reco_arch='crnn_vgg16_bn',
    pretrained=True
)

# Dokument laden
doc = DocumentFile.from_images("invoice.tif")

# OCR durchfuhren
result = model(doc)

# Text extrahieren
for page in result.pages:
    for block in page.blocks:
        for line in block.lines:
            text = ' '.join([word.value for word in line.words])
            print(text)
```

### Mit explizit deutschem Modell

```python
from doctr.models import ocr_predictor

# Deutsches Recognition-Modell
model = ocr_predictor(
    det_arch='db_resnet50',
    reco_arch='crnn_vgg16_bn',
    pretrained=True,
    assume_straight_pages=True  # Schneller fur gescannte Dokumente
)
```

---

## Vergleich: docTR vs PaddleOCR vs Surya CPU

| Kriterium | docTR | PaddleOCR v5 | Surya CPU |
|-----------|-------|--------------|-----------|
| **GPU** | Nein | Nein | Nein |
| **RAM** | ~1GB | ~2GB | ~4GB |
| **Deutsches Modell** | **JA** | Ja (Teil von 106) | Ja (Teil von 90+) |
| **Modellgrosse** | ~160MB | ~10MB | ~250MB |
| **Umlaut-Fokus** | **Hoch** | Mittel | Mittel |
| **Community** | Mittel | Sehr gross | Gross |

---

## Links

- **GitHub:** https://github.com/mindee/doctr
- **Dokumentation:** https://mindee.github.io/doctr/
- **PyPI:** https://pypi.org/project/python-doctr/

---

## Empfehlung fur unser System

| Aspekt | Bewertung |
|--------|-----------|
| **Testen?** | **JA** |
| **Prioritat** | Nach PaddleOCR |
| **Besonderheit** | Deutsches Modell |

### Warum docTR interessant ist

1. **Deutsches Modell** speziell verfugbar
2. **Sehr leichtgewichtig** (~1GB RAM)
3. **Gute API** fur Integration

### Wann docTR statt PaddleOCR?

- Wenn deutsche Umlaute kritisch sind
- Wenn minimaler RAM-Verbrauch wichtig ist
- Als zweite CPU-Alternative zum Vergleich

**Nachster Schritt:** Nach PaddleOCR-Tests docTR mit deutschem Modell evaluieren, besonders fur Umlaut-Genauigkeit.
