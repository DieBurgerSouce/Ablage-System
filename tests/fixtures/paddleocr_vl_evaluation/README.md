# PaddleOCR-VL 0.9B Evaluation Dataset

**Erstellt:** 2025-12-20
**Zweck:** Umfassende Evaluierung von PaddleOCR-VL 0.9B für deutsche Geschäftsdokumente
**Status:** Phase 1.2 - Dataset vorbereitet

---

## Übersicht

Dieses Dataset enthält 20 sorgfältig ausgewählte deutsche Geschäftsdokumente für die Evaluierung von PaddleOCR-VL 0.9B.

### Dokument-Verteilung

| Typ | Anzahl | Beschreibung |
|-----|--------|--------------|
| **Rechnungen** | 8 | Standard-Rechnungen mit IBAN, USt-IdNr., Tabellen |
| **Verträge** | 4 | Dienstleistungsverträge, Mietverträge, Kaufverträge |
| **Kontoauszüge** | 4 | Bank-Statements mit Transaktions-Tabellen |
| **Lieferscheine** | 2 | Versanddokumente mit Artikel-Listen |
| **Briefe** | 2 | Geschäftskorrespondenz |

### Qualitäts-Verteilung

| Qualität | Anzahl | DPI | Beschreibung |
|----------|--------|-----|--------------|
| **High** | 7 | 300+ | Saubere Scans, hohe Auflösung |
| **Medium** | 9 | 150-200 | Normale Qualität, leichte Rauschen |
| **Low** | 4 | <150 | Niedrige Qualität, Test für Robustheit |

---

## Dataset-Struktur

```
tests/fixtures/paddleocr_vl_evaluation/
├── README.md                    # Diese Datei
├── dataset_manifest.json        # Vollständige Dataset-Beschreibung
└── (Dokumente werden referenziert aus tests/fixtures/german_docs/)
```

**Hinweis:** Die tatsächlichen Dokumente bleiben in `tests/fixtures/german_docs/` - dieses Verzeichnis enthält nur die Manifest-Datei mit Referenzen.

---

## Dokument-Details

### Rechnungen (8 Dokumente)

1. **eval_001** - Standard invoice with IBAN, VAT ID, dates (High Quality)
2. **eval_002** - Invoice with multiple line items (High Quality)
3. **eval_003** - Invoice with payment terms (Medium Quality)
4. **eval_004** - Invoice with discounts (Medium Quality)
5. **eval_005** - Complex invoice with multiple sections (High Quality)
6. **eval_006** - Invoice with tax breakdown (Medium Quality)
7. **eval_007** - Table-based invoice format (High Quality, mit Tabellen)
8. **eval_008** - Structured table invoice (Medium Quality, mit Tabellen)

### Verträge (4 Dokumente)

9. **eval_009** - Service contract with multiple paragraphs (High Quality)
10. **eval_010** - Employment contract (High Quality)
11. **eval_011** - Rental agreement (Medium Quality)
12. **eval_012** - Purchase agreement (Medium Quality)

### Kontoauszüge (4 Dokumente)

13. **eval_013** - Bank statement with transaction table (High Quality, mit Tabellen)
14. **eval_014** - Account statement with multiple transactions (High Quality, mit Tabellen)
15. **eval_015** - Monthly account summary (Medium Quality, mit Tabellen)
16. **eval_016** - Detailed transaction list (Medium Quality, mit Tabellen)

### Lieferscheine (2 Dokumente)

17. **eval_017** - Delivery note with mixed content (Medium Quality, mit Tabellen)
18. **eval_018** - Shipping document with items list (Low Quality, mit Tabellen)

### Briefe (2 Dokumente)

19. **eval_019** - Formal business letter (High Quality)
20. **eval_020** - Official correspondence (Low Quality)

---

## Ground Truth Format

Jedes Dokument hat eine entsprechende JSON-Datei mit Ground Truth:

```json
{
  "filename": "invoice_001.png",
  "category": "invoices",
  "source": "synthetic",
  "expected_text": "Vollständiger Text...",
  "expected_entities": {
    "iban": ["DE89..."],
    "vat_id": ["DE..."],
    "date": ["22.11.2024"]
  },
  "has_umlauts": true,
  "has_tables": false,
  "language": "de"
}
```

**Pfade:** Alle Ground Truth JSON-Dateien befinden sich in `tests/fixtures/german_docs/{category}/{filename}.json`

---

## Evaluierungs-Kriterien

### Must-Have (für Production-Integration)

- ✅ **Umlaut-Accuracy ≥95%** (kritisch!)
- ✅ **VRAM <14GB** auf RTX 4080 (kritisch!)
- ✅ **Processing-Time <5s** pro Seite
- ✅ **Keine OOM-Fehler** in Tests
- ✅ **Mindestens 1 klarer Vorteil** gegenüber PP-OCRv5

### Nice-to-Have

- ⭐ Umlaut-Accuracy >98%
- ⭐ Processing-Time <3s pro Seite
- ⭐ Bessere Performance bei komplexen Layouts
- ⭐ Strukturierte Outputs (JSON/Markdown)

---

## Vergleichs-Backends

Die Evaluierung vergleicht PaddleOCR-VL 0.9B mit:

1. **PaddleOCR PP-OCRv5** (aktuell implementiert, CPU-only)
2. **Surya GPU** (Standard-Backend, GPU)
3. **DeepSeek-Janus-Pro** (Best-in-Class, GPU)

### Metriken

- **CER** (Character Error Rate)
- **WER** (Word Error Rate)
- **Umlaut Accuracy** (kritisch für deutsche Dokumente)
- **Processing Time** per Page
- **VRAM Peak Usage**
- **Confidence Scores**

---

## Verwendung

### Dataset laden

```python
import json
from pathlib import Path

manifest_path = Path("tests/fixtures/paddleocr_vl_evaluation/dataset_manifest.json")
with open(manifest_path) as f:
    dataset = json.load(f)

for doc in dataset["documents"]:
    image_path = doc["source"]
    gt_path = doc["ground_truth"]
    # Verarbeite Dokument...
```

### Ground Truth laden

```python
import json

with open("tests/fixtures/german_docs/invoices/invoice_001.json") as f:
    gt = json.load(f)

expected_text = gt["expected_text"]
expected_entities = gt["expected_entities"]
```

---

## Nächste Schritte

1. ✅ **Phase 1.2 abgeschlossen:** Dataset vorbereitet
2. ⏳ **Phase 2:** Docker-Isolation Setup
3. ⏳ **Phase 3:** Basic Functionality Test
4. ⏳ **Phase 4:** Vollständiger Benchmark-Lauf

---

## Lizenz

Alle Dokumente sind synthetisch generiert und unter CC0 (Public Domain) lizenziert.

---

*Dataset erstellt: 2025-12-20*
*Nächste Aktualisierung: Nach Benchmark-Phase*

