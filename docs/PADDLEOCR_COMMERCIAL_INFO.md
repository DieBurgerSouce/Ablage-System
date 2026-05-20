# PaddleOCR - Kommerzielle Lizenz-Analyse

**Stand:** 08. Dezember 2025
**Entwickler:** Baidu (PaddlePaddle Team)
**Repository:** https://github.com/PaddlePaddle/PaddleOCR

---

## Ubersicht

PaddleOCR PP-OCRv5 ist ein leichtgewichtiges, CPU-optimiertes OCR-System von Baidu. Es ist grundsatzlich **Apache 2.0 lizenziert**, hat aber eine **kritische Abhangigkeit** die beachtet werden muss.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **GPU erforderlich** | NEIN - CPU-optimiert |
| **RAM** | ~2GB |
| **Sprachen** | 106 (inkl. Deutsch) |
| **Modellgrosse** | ~10MB (Server) / ~3MB (Mobile) |
| **Benchmark** | 86.38% (PP-OCRv5 Server) |
| **Architektur** | Pipeline (Detection + Recognition) |

---

## LIZENZSTRUKTUR

### Hauptlizenz: Apache 2.0

```
┌─────────────────────────────────────────────────────────────┐
│                 PADDLEOCR LIZENZ                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PaddleOCR Code + Modelle: Apache 2.0                       │
│  ─────────────────────────────────────                      │
│  ✓ Kommerzielle Nutzung erlaubt                            │
│  ✓ Modifikation erlaubt                                    │
│  ✓ Verteilung erlaubt                                      │
│  ✓ Keine Copyleft-Anforderung                              │
│                                                             │
│  ABER: Abhangigkeiten prufen!                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### KRITISCHE ABHANGIGKEIT: PyMuPDF (AGPL-3.0)

**Das Problem:**

```
paddleocr
  └── PyMuPDF (fur PDF-Verarbeitung)
        └── AGPL-3.0 Lizenz!
```

**Was AGPL-3.0 bedeutet:**

```
AGPL-3.0 = "Affero GPL" = Starkste Copyleft-Lizenz

Wenn du AGPL-Code nutzt:
  → Dein GESAMTER Code muss unter AGPL veroffentlicht werden
  → Gilt auch fur SaaS/Server-Nutzung (anders als GPL!)
  → Jeder Nutzer hat Recht auf Quellcode
```

**Wann wird PyMuPDF geladen?**

```python
# PyMuPDF wird geladen wenn:
result = ocr.ocr('document.pdf')  # <-- PDF-Datei!

# PyMuPDF wird NICHT geladen wenn:
result = ocr.ocr('document.png')  # <-- Bild-Datei
result = ocr.ocr(numpy_array)     # <-- Numpy Array
```

---

## LOSUNGSWEGE FUR KOMMERZIELLE NUTZUNG

### Option 1: Nur Bilder verarbeiten (EMPFOHLEN)

**Strategie:** Vermeide PDF-Verarbeitung in PaddleOCR, konvertiere PDFs vorher.

**Implementierung:**

```python
# SCHRITT 1: PDF zu Bildern mit pdf2image (Poppler, GPL-freundlich)
from pdf2image import convert_from_path
import numpy as np
from paddleocr import PaddleOCR

# pdf2image nutzt Poppler (GPL, aber als separater Prozess = OK)
# Oder benutze PyPDF2 + Pillow (beides BSD/MIT)

def convert_pdf_safely(pdf_path: str) -> list:
    """Konvertiert PDF zu Bildern OHNE PyMuPDF."""
    # Option A: pdf2image (Poppler als externes Tool)
    images = convert_from_path(pdf_path, dpi=300)
    return [np.array(img) for img in images]

# SCHRITT 2: PaddleOCR nur mit Bildern
ocr = PaddleOCR(use_angle_cls=True, lang='german', use_gpu=False)

def process_document(file_path: str) -> str:
    """Verarbeitet Dokument sicher ohne AGPL-Abhangigkeit."""

    if file_path.lower().endswith('.pdf'):
        # PDF vorher konvertieren
        images = convert_pdf_safely(file_path)
        results = []
        for img in images:
            result = ocr.ocr(img, cls=True)  # Numpy array, kein PDF!
            results.extend(extract_text(result))
        return '\n'.join(results)
    else:
        # Bild direkt verarbeiten
        result = ocr.ocr(file_path, cls=True)
        return extract_text(result)

def extract_text(ocr_result) -> list:
    """Extrahiert Text aus PaddleOCR Ergebnis."""
    texts = []
    for line in ocr_result[0]:
        text = line[1][0]
        texts.append(text)
    return texts
```

**Alternative PDF-Konverter (keine AGPL):**

| Bibliothek | Lizenz | Methode |
|------------|--------|---------|
| **pdf2image** | MIT | Nutzt Poppler (extern) |
| **PyPDF2** | BSD | Reines Python |
| **pikepdf** | MPL-2.0 | QPDF-basiert |
| **pdfplumber** | MIT | Nutzt pdfminer |

### Option 2: PyMuPDF explizit ausschliessen

**In requirements.txt:**

```txt
paddleocr>=2.7.0
# PyMuPDF NICHT installieren - AGPL!
pdf2image>=1.16.0
Pillow>=9.0.0
```

**Installation ohne PyMuPDF:**

```bash
# Installiere PaddleOCR ohne optionale PDF-Dependencies
pip install paddleocr --no-deps
pip install paddlepaddle  # Basis-Framework

# Installiere nur benotigte Dependencies manuell
pip install numpy opencv-python Pillow shapely pyclipper
pip install pdf2image  # Fur PDF-Konvertierung (MIT)
```

### Option 3: Docker-Isolation

**Konzept:** PyMuPDF in isoliertem Container, keine direkte Code-Verlinkung.

```yaml
# docker-compose.yml
services:
  pdf-converter:
    image: pdf-converter:latest  # Separater Service mit PyMuPDF
    # AGPL gilt nur fur diesen Container

  ocr-service:
    image: paddleocr:latest  # Dein Haupt-Service
    # Kommuniziert uber API, keine Code-Verlinkung
```

**ACHTUNG:** Diese Interpretation ist rechtlich umstritten! Konsultiere einen Anwalt.

---

## VOLLSTANDIGER SICHERER SETUP

### requirements.txt (AGPL-frei)

```txt
# PaddleOCR Core
paddlepaddle>=2.5.0
paddleocr>=2.7.0

# PDF-Verarbeitung (AGPL-frei)
pdf2image>=1.16.0
Pillow>=10.0.0

# NICHT INSTALLIEREN:
# PyMuPDF - AGPL-3.0!
# fitz - ist PyMuPDF!
```

### Sichere OCR-Agent Implementierung

```python
"""
PaddleOCR Agent - AGPL-freie Implementierung
"""
import os
from typing import Optional
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

# Prufe ob PyMuPDF versehentlich installiert ist
try:
    import fitz
    raise RuntimeError(
        "PyMuPDF (fitz) ist installiert! "
        "Dies wurde AGPL-3.0 Lizenzanforderungen auslosen. "
        "Bitte deinstallieren: pip uninstall PyMuPDF"
    )
except ImportError:
    pass  # Gut - PyMuPDF ist nicht installiert

class PaddleOCRAgent:
    """AGPL-freier PaddleOCR Agent."""

    def __init__(self, language: str = 'german'):
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=language,
            use_gpu=False,
            show_log=False
        )

    def process_image(self, image_path: str) -> dict:
        """Verarbeitet ein Bild (kein PDF!)."""
        if image_path.lower().endswith('.pdf'):
            raise ValueError(
                "PDF-Dateien mussen vorher konvertiert werden! "
                "Nutze convert_pdf_to_images() zuerst."
            )

        result = self.ocr.ocr(image_path, cls=True)
        return self._format_result(result)

    def process_numpy(self, image_array: np.ndarray) -> dict:
        """Verarbeitet ein Numpy-Array."""
        result = self.ocr.ocr(image_array, cls=True)
        return self._format_result(result)

    def _format_result(self, ocr_result) -> dict:
        """Formatiert OCR-Ergebnis."""
        if not ocr_result or not ocr_result[0]:
            return {'text': '', 'confidence': 0.0, 'boxes': []}

        texts = []
        confidences = []
        boxes = []

        for line in ocr_result[0]:
            box = line[0]
            text = line[1][0]
            conf = line[1][1]

            texts.append(text)
            confidences.append(conf)
            boxes.append(box)

        return {
            'text': '\n'.join(texts),
            'confidence': sum(confidences) / len(confidences) if confidences else 0.0,
            'boxes': boxes
        }


def convert_pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    """
    Konvertiert PDF zu Bildern OHNE PyMuPDF.
    Nutzt pdf2image (MIT-Lizenz) mit Poppler.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "pdf2image nicht installiert. "
            "Installiere mit: pip install pdf2image"
        )

    images = convert_from_path(pdf_path, dpi=dpi)
    return [np.array(img.convert('RGB')) for img in images]


# Beispiel-Nutzung
if __name__ == '__main__':
    agent = PaddleOCRAgent(language='german')

    # Bild verarbeiten
    result = agent.process_image('rechnung.png')
    print(result['text'])

    # PDF verarbeiten (sicher)
    images = convert_pdf_to_images('rechnung.pdf')
    for i, img in enumerate(images):
        result = agent.process_numpy(img)
        print(f"Seite {i+1}: {result['text'][:200]}...")
```

---

## LIZENZ-CHECKLISTE

### Vor Veroffentlichung prufen:

```bash
# Prufe installierte Pakete auf AGPL
pip list | grep -i mupdf
pip list | grep -i fitz

# Sollte LEER sein! Wenn nicht:
pip uninstall PyMuPDF

# Prufe Abhangigkeiten
pip show paddleocr | grep Requires
```

### Lizenz-Audit Script:

```python
"""Pruft auf AGPL-Abhangigkeiten."""
import pkg_resources

AGPL_PACKAGES = ['PyMuPDF', 'fitz']
GPL_PACKAGES = ['PyMuPDF', 'fitz', 'ghostscript']

installed = {pkg.key for pkg in pkg_resources.working_set}

issues = []
for pkg in AGPL_PACKAGES:
    if pkg.lower() in installed:
        issues.append(f"AGPL-Paket gefunden: {pkg}")

if issues:
    print("LIZENZ-PROBLEME GEFUNDEN:")
    for issue in issues:
        print(f"  - {issue}")
    exit(1)
else:
    print("Keine AGPL-Abhangigkeiten gefunden.")
```

---

## ZUSAMMENFASSUNG

### Kann ich PaddleOCR kommerziell nutzen?

| Frage | Antwort |
|-------|---------|
| PaddleOCR selbst? | JA (Apache 2.0) |
| Mit PDF-Support? | NEIN (PyMuPDF = AGPL) |
| Mit Bild-Input? | JA |
| Mit pdf2image fur PDFs? | JA |
| Modelle weiterverteilen? | JA (Apache 2.0) |

### Empfehlung

```
FUR KOMMERZIELLE NUTZUNG:

1. Installiere PaddleOCR OHNE PyMuPDF
2. Nutze pdf2image fur PDF-Konvertierung
3. Verarbeite nur Bilder/Numpy-Arrays mit PaddleOCR
4. Fuhre Lizenz-Audit vor Release durch

VERMEIDEN:
- ocr.ocr('datei.pdf') direkt aufrufen
- PyMuPDF/fitz importieren
- PDF-Features von PaddleOCR nutzen
```

---

## TECHNISCHE PERFORMANCE

| Metrik | Wert |
|--------|------|
| **Genauigkeit** | 86.38% (PP-OCRv5 Server) |
| **Zeit/Seite** | ~1-2s (CPU) |
| **RAM** | ~2GB |
| **Sprachen** | 106 (inkl. Deutsch) |

### Vergleich mit Surya

| Kriterium | PaddleOCR | Surya GPU |
|-----------|-----------|-----------|
| **Lizenz** | Apache 2.0 | GPL-3.0 + Custom |
| **Kommerziell** | JA (ohne PDF) | Nur mit Lizenz |
| **GPU** | Optional | Ja |
| **Genauigkeit** | 86% | 97% |
| **Deutsche Umlaute** | Gut | Sehr gut |

---

## LINKS

- **GitHub:** https://github.com/PaddlePaddle/PaddleOCR
- **Dokumentation:** https://paddlepaddle.github.io/PaddleOCR
- **PyPI:** https://pypi.org/project/paddleocr/
- **Lizenz:** Apache 2.0

---

## RISIKO-BEWERTUNG

| Risiko | Level | Beschreibung |
|--------|-------|--------------|
| AGPL-Verletzung durch PyMuPDF | HOCH | Wenn PDF-Feature genutzt wird |
| Apache 2.0 Verletzung | NIEDRIG | Nur Attribution erforderlich |
| Patent-Risiko | NIEDRIG | Apache 2.0 enthalt Patent-Grant |

**Meine Empfehlung:**

PaddleOCR ist eine gute CPU-Alternative, aber:
1. **NIEMALS** PDF-Dateien direkt verarbeiten
2. **IMMER** vorher zu Bildern konvertieren
3. **REGELMASIG** Lizenz-Audit durchfuhren
4. **DOKUMENTIEREN** dass PyMuPDF nicht verwendet wird
