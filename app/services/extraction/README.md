# Extraction Services

Modulare Pattern Library fuer Document Data Extraction im Ablage-System.

## Uebersicht

Das Extraction-Modul bietet layout-unabhaengige Datenextraktion fuer:
- Payment Terms (Zahlungsziele, Skonto-Staffeln)
- Amounts (Netto, Brutto, MwSt, Rabatte)
- Line Items (Rechnungspositionen)
- Cross-Field Validation (Plausibilitaetspruefungen)

Designed fuer CPU-Systeme ohne LLM-Abhaengigkeit.

## Architektur

```
extraction/
├── base.py                     # Basisklassen und Datentypen
│   ├── PatternMatch            # Match-Ergebnis mit Kontext
│   ├── Pattern                 # Regex-Pattern Definition
│   ├── PatternRegistry         # Pattern-Verwaltung
│   ├── ExtractionConfig        # Konfiguration
│   ├── ExtractedAmount         # Extrahierter Betrag
│   ├── DocumentAmounts         # Alle Betraege eines Dokuments
│   ├── DiscountTier            # Skonto-Staffel
│   └── ValidationResult        # Validierungsergebnis
│
├── config.py                   # Globale Konfiguration
│   ├── GERMAN_VAT_RATES        # Deutsche MwSt-Saetze
│   └── get_default_config()    # Standard-Einstellungen
│
├── patterns/                   # Pattern-Definitionen
│   ├── amount_patterns.py      # Betrags-Patterns (EUR, CHF)
│   ├── date_patterns.py        # Datums-Patterns
│   ├── payment_patterns.py     # Zahlungsziel-Patterns
│   └── reference_patterns.py   # Referenz-Patterns (IBAN, etc.)
│
├── extractors/                 # Spezifische Extraktoren
│   ├── amount_extractor.py     # SmartAmountExtractor
│   ├── payment_extractor.py    # PaymentTermsExtractor
│   └── line_item_extractor.py  # EnhancedLineItemExtractor
│
├── validators/                 # Validierungslogik
│   └── cross_field_validator.py # CrossFieldValidator
│
└── integration.py              # Integration in Pipeline
    ├── EnhancedExtractionAdapter
    ├── apply_enhanced_extraction()
    └── get_enhanced_extraction_adapter()
```

## Komponenten

### 1. Pattern-System

Das Pattern-System ermoeglicht flexible Regex-basierte Extraktion:

```python
from app.services.extraction import Pattern, PatternMatch

# Pattern definieren
pattern = Pattern(
    name="german_amount",
    regex=r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*(EUR|€)?",
    confidence=0.9,
    description="Deutsche Betragsformate"
)
```

### 2. Amount Extractor

Extrahiert und klassifiziert Betraege:

```python
from app.services.extraction import SmartAmountExtractor

extractor = SmartAmountExtractor()
result = extractor.extract(text)

# Ergebnis: AmountExtractionResult
print(result.total)      # Gesamtbetrag
print(result.net)        # Nettobetrag
print(result.vat)        # MwSt
print(result.gross)      # Bruttobetrag
```

### 3. Payment Terms Extractor

Erkennt Zahlungsbedingungen und Skonto:

```python
from app.services.extraction import PaymentTermsExtractor

extractor = PaymentTermsExtractor()
terms = extractor.extract(text, invoice_date=date.today())

# Ergebnis: ExtractedPaymentTerms
print(terms.due_date)         # Faelligkeitsdatum
print(terms.payment_days)     # Zahlungsziel in Tagen
print(terms.discount_tiers)   # Skonto-Staffeln
```

### 4. Line Item Extractor

Extrahiert Rechnungspositionen:

```python
from app.services.extraction import EnhancedLineItemExtractor

extractor = EnhancedLineItemExtractor()
items = extractor.extract(text, tables=table_data)

# Ergebnis: List[ExtractedLineItem]
for item in items:
    print(item.description)
    print(item.quantity)
    print(item.unit_price)
    print(item.total)
```

### 5. Cross-Field Validator

Validiert Konsistenz zwischen Feldern:

```python
from app.services.extraction import CrossFieldValidator, InvoiceValidationInput

validator = CrossFieldValidator()
input_data = InvoiceValidationInput(
    line_items=items,
    total_net=net_amount,
    total_vat=vat_amount,
    total_gross=gross_amount
)

result = validator.validate(input_data)
# Prueft: Summe Positionen = Netto, Netto + MwSt = Brutto, etc.
```

## Integration

### Vollstaendige Extraktion

```python
from app.services.extraction import (
    EnhancedExtractionAdapter,
    apply_enhanced_extraction,
)
from datetime import date

# Option 1: Adapter direkt nutzen
adapter = EnhancedExtractionAdapter()
result = adapter.extract_all(
    text=ocr_text,
    invoice_date=date.today(),
    tables=extracted_tables
)

print(result.amounts)         # DocumentAmounts
print(result.payment_terms)   # ExtractedPaymentTerms
print(result.line_items)      # List[ExtractedLineItem]
print(result.validation)      # ValidationResult

# Option 2: Convenience-Funktion mit Merge
merged_data = apply_enhanced_extraction(
    text=ocr_text,
    invoice_date=date.today(),
    tables=extracted_tables,
    existing_data=previous_extraction
)
```

### Feature Toggle

```python
from app.services.extraction import ENABLE_ENHANCED_EXTRACTION

if ENABLE_ENHANCED_EXTRACTION:
    # Nutze Enhanced Extraction
    result = apply_enhanced_extraction(text, invoice_date)
else:
    # Fallback auf Legacy-Extraktion
    result = legacy_extraction(text)
```

## Unterstuetzte Formate

### Betraege

| Format | Beispiel | Waehrung |
|--------|----------|----------|
| Deutsch | 1.234,56 EUR | EUR |
| Deutsch | 1.234,56 € | EUR |
| Schweiz | CHF 1'234.56 | CHF |
| International | 1,234.56 USD | USD |

### Zahlungsziele

| Muster | Beispiel |
|--------|----------|
| Tage | "Zahlbar innerhalb 30 Tagen" |
| Datum | "Faellig bis 31.12.2025" |
| Netto | "30 Tage netto" |
| Sofort | "Zahlbar sofort" |

### Skonto

| Muster | Beispiel |
|--------|----------|
| Prozent + Tage | "2% Skonto bei Zahlung innerhalb 10 Tagen" |
| Staffel | "3% bei 7 Tagen, 2% bei 14 Tagen" |
| Abzug | "Bei Zahlung bis 15.01. 2% Abzug" |

## Konfiguration

```python
from app.services.extraction import ExtractionConfig, get_default_config

# Standard-Konfiguration
config = get_default_config()

# Angepasste Konfiguration
custom_config = ExtractionConfig(
    min_confidence=0.7,           # Mindest-Confidence
    max_amount=1_000_000.00,      # Maximaler Betrag
    default_currency="EUR",       # Standard-Waehrung
    enable_cross_validation=True, # Cross-Field Validation
)
```

## MwSt-Saetze

Unterstuetzte deutsche MwSt-Saetze:

```python
GERMAN_VAT_RATES = {
    0.0: "Steuerfrei",
    7.0: "Ermaessigt (7%)",
    19.0: "Regelsteuersatz (19%)",
}
```

## Fehlerbehandlung

```python
from app.services.extraction import ValidationResult, Severity

result = validator.validate(input_data)

for issue in result.issues:
    if issue.severity == Severity.ERROR:
        logger.error(f"Validierungsfehler: {issue.message}")
    elif issue.severity == Severity.WARNING:
        logger.warning(f"Warnung: {issue.message}")
```

## Performance

- **CPU-optimiert**: Keine GPU erforderlich
- **Parallelisierbar**: Patterns werden unabhaengig ausgewertet
- **Caching**: PatternRegistry cached kompilierte Regexe
- **Streaming**: Grosse Dokumente koennen chunked verarbeitet werden

## Erweiterung

### Neues Pattern hinzufuegen

```python
from app.services.extraction import Pattern, PatternRegistry

# Pattern definieren
new_pattern = Pattern(
    name="custom_reference",
    regex=r"REF[:-]?\s*(\d{6,12})",
    confidence=0.85,
    description="Custom Reference Number"
)

# Zur Registry hinzufuegen
registry = PatternRegistry()
registry.register(new_pattern)
```

### Neuer Extractor

```python
from app.services.extraction.base import BaseExtractor

class CustomExtractor(BaseExtractor):
    def extract(self, text: str) -> Any:
        # Implementierung
        pass
```

## Abhaengigkeiten

- Python 3.11+
- structlog (Logging)
- dataclasses (Datenstrukturen)
- Keine externen ML-Bibliotheken erforderlich

## Verwandte Module

- `app/services/ocr_service.py` - OCR Pipeline (liefert Text)
- `app/services/banking/` - Banking-Integration
- `app/services/datev/` - DATEV Export
- `app/services/document_services/` - Dokument-CRUD
