# E-Invoice Services (XRechnung / ZUGFeRD)

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält Services für die Verarbeitung elektronischer Rechnungen nach den deutschen und europäischen Standards XRechnung und ZUGFeRD.

---

## Services

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **ParserService** | `parser_service.py` | XML/PDF Parsing von E-Rechnungen |
| **GeneratorService** | `generator_service.py` | Erstellung von E-Rechnungen |
| **ValidatorService** | `validator_service.py` | Validierung gegen Standards |
| **MustangClient** | `mustang_client.py` | Integration mit Mustang Library |
| **EInvoiceModels** | `einvoice_models.py` | Pydantic-Modelle für E-Rechnungen |

---

## Unterstützte Formate

| Format | Version | Beschreibung |
|--------|---------|--------------|
| XRechnung | 3.0 | Deutscher Standard für B2G |
| ZUGFeRD | 2.1.1 | Hybrid-Format (PDF + XML) |
| Factur-X | 1.0 | Französisches ZUGFeRD-Äquivalent |
| EN 16931 | 1.3 | Europäische Norm |

---

## ZUGFeRD Profile

| Profil | Beschreibung | Use Case |
|--------|--------------|----------|
| `MINIMUM` | Minimalanforderungen | Einfache Rechnungen |
| `BASIC_WL` | Basic ohne Line-Items | Pauschalrechnungen |
| `BASIC` | Standard-Profil | Normale Rechnungen |
| `EN16931` (Comfort) | EU-konform | B2G, International |
| `EXTENDED` | Alle Features | Komplexe Rechnungen |

---

## ParserService

Extrahiert strukturierte Daten aus E-Rechnungen.

### Unterstützte Eingaben

- XRechnung XML (`.xml`)
- ZUGFeRD PDF (`.pdf` mit eingebettetem XML)
- Cross-Industry Invoice (CII) XML
- Universal Business Language (UBL) XML

### Extrahierte Daten

```python
class ParsedInvoice(BaseModel):
    # Kopfdaten
    invoice_number: str
    invoice_date: date
    due_date: Optional[date]
    currency: str = "EUR"

    # Beträge
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal

    # Parteien
    seller: Party
    buyer: Party

    # Positionen
    line_items: List[LineItem]

    # Zahlungsinformationen
    payment_terms: Optional[PaymentTerms]
    bank_account: Optional[BankAccount]

    # Referenzen
    order_reference: Optional[str]
    delivery_note_reference: Optional[str]
```

### Verwendung

```python
from app.services.einvoice.parser_service import EInvoiceParserService

parser = EInvoiceParserService()

# XML parsen
invoice = await parser.parse_xml(xml_content)

# PDF mit eingebettetem XML parsen
invoice = await parser.parse_pdf(pdf_content)

# Format automatisch erkennen
invoice = await parser.parse_auto(file_content, filename)
```

---

## GeneratorService

Erstellt E-Rechnungen aus Ablage-Dokumenten.

### Unterstützte Ausgaben

- XRechnung 3.0 (CII XML)
- ZUGFeRD 2.1.1 (PDF/A-3 mit eingebettetem XML)
- Factur-X 1.0

### Verwendung

```python
from app.services.einvoice.generator_service import EInvoiceGeneratorService

generator = EInvoiceGeneratorService()

# XRechnung XML erstellen
xml = await generator.generate_xrechnung(
    invoice_data=invoice_data,
    seller=seller_party,
    buyer=buyer_party
)

# ZUGFeRD PDF erstellen
pdf = await generator.generate_zugferd(
    invoice_data=invoice_data,
    original_pdf=original_pdf_bytes,
    profile="EN16931"
)
```

### XRechnung für öffentliche Auftraggeber

```python
# Mit Leitweg-ID für B2G
xml = await generator.generate_xrechnung(
    invoice_data=invoice_data,
    leitweg_id="04011000-12345-12",  # Pflicht für B2G
    buyer_reference="Bestellnummer-123"
)
```

---

## ValidatorService

Validiert E-Rechnungen gegen offizielle Schematrons und XSDs.

### Validierungsebenen

| Ebene | Beschreibung |
|-------|--------------|
| `syntax` | XML-Wohlgeformtheit |
| `schema` | XSD-Konformität |
| `schematron` | Geschäftsregeln |
| `semantic` | Semantische Prüfung |

### Validierungsergebnis

```python
class ValidationResult(BaseModel):
    is_valid: bool
    format_detected: str  # "XRechnung", "ZUGFeRD", etc.
    profile: Optional[str]
    errors: List[ValidationError]
    warnings: List[ValidationWarning]

class ValidationError(BaseModel):
    code: str       # z.B. "BR-01"
    location: str   # XPath
    message: str    # Deutsche Fehlermeldung
    severity: str   # "error", "fatal"
```

### Verwendung

```python
from app.services.einvoice.validator_service import EInvoiceValidatorService

validator = EInvoiceValidatorService()

result = await validator.validate(
    content=xml_content,
    format="XRechnung",
    profile="EN16931"
)

if not result.is_valid:
    for error in result.errors:
        print(f"{error.code}: {error.message}")
```

### Wichtige Geschäftsregeln (BR)

| Regel | Beschreibung |
|-------|--------------|
| BR-01 | Rechnungsnummer ist Pflicht |
| BR-02 | Rechnungsdatum ist Pflicht |
| BR-03 | Käuferidentifikation erforderlich |
| BR-04 | Verkäuferidentifikation erforderlich |
| BR-05 | Währungscode ist Pflicht |
| BR-06 | Fälliges Rechnungsendbetrag ist Pflicht |

---

## MustangClient

Integration mit der Mustang Java-Bibliothek für ZUGFeRD.

### Architektur

```
Python Service
     ↓
HTTP-Aufrufe (REST)
     ↓
Mustang Microservice (Java)
     ↓
Mustang Library (ZUGFeRD)
```

### Konfiguration

```python
MUSTANG_SERVICE_URL: str = "http://localhost:8081"
MUSTANG_TIMEOUT: int = 30
```

### Funktionen

- PDF/A-3 Konvertierung
- XML-Einbettung in PDF
- PDF-Signatur (optional)
- Validierung via Mustang

---

## EInvoiceModels

Pydantic-Modelle für die interne Datenrepräsentation.

### Hauptmodelle

```python
class Party(BaseModel):
    """Rechnungspartei (Käufer/Verkäufer)."""
    name: str
    street: Optional[str]
    city: Optional[str]
    postal_code: Optional[str]
    country_code: str = "DE"
    vat_id: Optional[str]
    tax_number: Optional[str]
    email: Optional[str]
    phone: Optional[str]

class LineItem(BaseModel):
    """Rechnungsposition."""
    position: int
    description: str
    quantity: Decimal
    unit: str  # "C62" (Stück), "HUR" (Stunde), etc.
    unit_price: Decimal
    net_amount: Decimal
    vat_rate: Decimal
    vat_category: str  # "S" (Standard), "Z" (Zero), etc.

class PaymentTerms(BaseModel):
    """Zahlungsbedingungen."""
    due_date: Optional[date]
    payment_means: str  # "30" (Bank), "58" (SEPA)
    payment_id: Optional[str]
    skonto_percent: Optional[Decimal]
    skonto_days: Optional[int]
    text: Optional[str]

class BankAccount(BaseModel):
    """Bankverbindung."""
    iban: str
    bic: Optional[str]
    bank_name: Optional[str]
    account_holder: Optional[str]
```

---

## API Endpoints

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/api/v1/einvoice/parse` | POST | E-Rechnung parsen |
| `/api/v1/einvoice/generate` | POST | E-Rechnung generieren |
| `/api/v1/einvoice/validate` | POST | E-Rechnung validieren |
| `/api/v1/einvoice/convert` | POST | Format konvertieren |

---

## Celery Tasks

| Task | Beschreibung |
|------|--------------|
| `einvoice.parse_uploaded` | Hochgeladene E-Rechnung parsen |
| `einvoice.generate_batch` | Batch-Generierung |
| `einvoice.validate_batch` | Batch-Validierung |

---

## Fehler-Codes

| Code | Beschreibung |
|------|--------------|
| `EINV_PARSE_FAILED` | Parsing fehlgeschlagen |
| `EINV_INVALID_FORMAT` | Unbekanntes Format |
| `EINV_VALIDATION_FAILED` | Validierung fehlgeschlagen |
| `EINV_GENERATION_FAILED` | Generierung fehlgeschlagen |
| `EINV_MISSING_FIELD` | Pflichtfeld fehlt |

---

## Sicherheit

1. **XML Security**: XXE-Protection, Entity-Expansion-Limits
2. **PDF Security**: Signaturprüfung, Integritätsprüfung
3. **Input Validation**: Strikte Validierung aller Eingaben
4. **Audit Logging**: Alle E-Rechnung-Operationen protokolliert
