# OCR Benchmark Dataset

Benchmark-Datensatz für die Qualitätsmessung der OCR-Backends im Ablage-System.

## Struktur

```
data/benchmarks/
├── schema.json                     # JSON-Schema für Samples
├── README.md                       # Diese Datei
├── samples/                        # Ground-Truth Samples
│   ├── sample_invoice_001.json
│   ├── sample_contract_001.json
│   ├── sample_fraktur_001.json
│   ├── sample_letter_001.json
│   └── sample_table_001.json
├── german_documents/               # Dokumentbilder (nach Typ)
│   ├── invoices/
│   ├── contracts/
│   ├── fraktur/
│   └── letters/
└── validation_sets/                # Validierungstests
    ├── umlaut_test.json
    └── compound_words_test.json
```

## Verwendung

### Python API

```python
from app.ml.benchmark_dataset import get_benchmark_dataset

# Dataset laden
dataset = get_benchmark_dataset()

# Samples auflisten
for sample in dataset.get_samples(document_type="invoice"):
    print(f"{sample.id}: {sample.difficulty}")

# Backend evaluieren
def my_ocr_function(image_path: str) -> str:
    # OCR durchführen
    return extracted_text

results = dataset.evaluate_backend("my_backend", my_ocr_function)

# Report generieren
report = dataset.generate_report("my_backend", results)
print(f"Durchschnittliche CER: {report.avg_cer:.2%}")
```

### Neues Sample hinzufügen

```python
dataset.add_sample(
    image_path="german_documents/invoices/neue_rechnung.png",
    ground_truth="Der korrekte Text...",
    document_type="invoice",
    language="de",
    difficulty="medium",
    has_tables=True,
)
```

## Metriken

- **CER** (Character Error Rate): Zeichenfehlerrate
- **WER** (Word Error Rate): Wortfehlerrate
- **Umlaut-Genauigkeit**: Erkennung von ä, ö, ü, ß
- **Großschreibungs-Genauigkeit**: Deutsche Substantive

## Dokumenttypen

| Typ | Beschreibung | Schwierigkeit |
|-----|--------------|---------------|
| `invoice` | Rechnungen | mittel |
| `contract` | Verträge | mittel |
| `letter` | Geschäftsbriefe | leicht |
| `fraktur` | Historische Frakturschrift | schwer |
| `table` | Tabellen-Dokumente | schwer |
| `form` | Formulare | mittel |
| `handwritten` | Handschrift | schwer |

## Qualitätsziele

- **CER < 5%** für Standard-Dokumente
- **CER < 10%** für Fraktur-Dokumente
- **Umlaut-Genauigkeit = 100%** (geschäftskritisch)
