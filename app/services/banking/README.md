# Banking Services

Enterprise-Level Banking-Integration fuer das Ablage-System.

## Uebersicht

Das Banking-Modul bietet umfassende Funktionalitaet fuer:
- Multi-Bank Statement Import (CSV, MT940, CAMT.053)
- Automatische Transaktions-Kategorisierung
- Intelligentes Matching von Zahlungen zu Rechnungen
- Mahnwesen (Dunning) mit konfigurierbaren Stufen
- Cash-Flow-Analyse und Forecasting
- Faelligkeitsberichte (Aging Reports)
- TAN-Handling fuer Online-Banking

## Architektur

```
banking/
├── parsers/                    # Statement-Parser
│   ├── base.py                 # BaseParser, ParseResult, ParsedTransaction
│   ├── csv_parser.py           # GenericCSVParser
│   ├── mt940_parser.py         # MT940/SWIFT Parser
│   ├── camt053_parser.py       # ISO 20022 CAMT.053 Parser
│   └── bank_csv/               # Bank-spezifische Parser
│       ├── commerzbank.py      # Commerzbank CSV
│       ├── deutsche_bank.py    # Deutsche Bank CSV
│       ├── dkb.py              # DKB CSV mit Metadaten-Header
│       ├── ing.py              # ING-DiBa CSV
│       ├── n26.py              # N26 CSV (Komma-separiert, Englisch)
│       ├── sparkasse.py        # Sparkasse CSV mit SEPA-Feldern
│       └── volksbank.py        # Volksbank/Raiffeisenbank CSV
│
├── account_service.py          # IBAN-Validierung, Kontooperationen
├── import_service.py           # Statement-Import mit Auto-Detection
├── transaction_service.py      # Transaktionsverwaltung
├── reconciliation_service.py   # Payment-Invoice Matching
├── reference_parser.py         # Verwendungszweck-Analyse
│
├── dunning_service.py          # Mahnwesen
├── dunning_stage_service.py    # Mahnstufen-Konfiguration
├── mahn_task_service.py        # Celery Tasks fuer Mahnungen
│
├── payment_service.py          # Zahlungsabwicklung
├── cash_flow_service.py        # Cash-Flow-Analyse
├── aging_report_service.py     # Faelligkeitsberichte
│
├── tan_handler_service.py      # TAN-Verarbeitung
├── models.py                   # Datenmodelle
└── utils.py                    # IBAN/BIC Maskierung
```

## Parser

### Unterstuetzte Formate

| Format | Parser | Konfidenz-Marker |
|--------|--------|------------------|
| MT940 (SWIFT) | `MT940Parser` | `:20:`, `:60:`, `:61:`, `:86:` |
| CAMT.053 (ISO 20022) | `CAMT053Parser` | XML mit `camt.053` Namespace |
| Commerzbank CSV | `CommerzbankCSVParser` | `Auftraggeber / Beguenstigter` |
| Deutsche Bank CSV | `DeutscheBankCSVParser` | `Beneficiary / Originator` |
| DKB CSV | `DKBCSVParser` | `Betrag (EUR)` |
| ING CSV | `INGCSVParser` | `Auftraggeber/Empfaenger` |
| N26 CSV | `N26CSVParser` | `Payee` + `Amount (EUR)` |
| Sparkasse CSV | `SparkasseCSVParser` | `Glaeubiger ID`, `Mandatsreferenz` |
| Volksbank CSV | `VolksbankCSVParser` | `Empfaenger/Zahlungspflichtiger` |

### Automatische Format-Erkennung

```python
from app.services.banking.parsers import detect_format

content = open("kontoauszug.csv", "rb").read()
results = detect_format(content, filename="kontoauszug.csv")

# results = [(ParserClass, confidence), ...]
parser_cls, confidence = results[0]
parser = parser_cls()
result = parser.parse(content)
```

### Security

- **XXE Protection**: CAMT.053 Parser verwendet `defusedxml` gegen XML External Entity Attacks
- **IBAN Masking**: Sichere Log-Ausgaben mit `mask_iban()`, `mask_bic()`
- **Input Validation**: Alle Parser validieren Eingabeformate

## Transaktions-Matching

Der `ReconciliationService` matched automatisch:

1. **SEPA End-to-End-ID**: Hoechste Prioritaet
2. **Rechnungsnummer im Verwendungszweck**: Pattern-basiert
3. **Kundennummer + Betrag**: Fuzzy Matching
4. **Creditor-ID (Lastschriften)**: SEPA Mandatsreferenz

## Mahnwesen

Konfigurierbare Mahnstufen mit:
- Automatischen Erinnerungen
- Eskalationspfaden
- Celery-basierter Verarbeitung
- Compliance-konformer Dokumentation

## Verwendungszweck-Analyse

Der `ReferenceParser` extrahiert:
- Rechnungsnummern (RE, RG, INV, etc.)
- Kundennummern (KD, KUNDE, etc.)
- Bestellnummern (BEST, ORDER, etc.)
- SEPA-Referenzen (EREF, MREF, CRED)

```python
from app.services.banking.parsers.base import BaseParser

parser = BaseParser()
refs = parser.parse_reference_text("Rechnung Nr. 2024-001 EREF+END2END-001")
# {
#     "invoice_numbers": ["2024-001"],
#     "end_to_end_ids": ["END2END-001"],
#     ...
# }
```

## Tests

```bash
# Unit Tests
pytest tests/unit/services/banking/ -v

# Spezifische Parser Tests
pytest tests/unit/services/banking/parsers/test_comprehensive_parsers.py -v

# Coverage
pytest tests/unit/services/banking/ --cov=app.services.banking --cov-report=html
```

## Konfiguration

Umgebungsvariablen in `.env`:

```
# Banking Import
BANKING_IMPORT_BATCH_SIZE=100
BANKING_IMPORT_MAX_FILE_SIZE_MB=50

# Mahnwesen
DUNNING_ENABLED=true
DUNNING_REMINDER_DAYS=14,28,42
DUNNING_ESCALATION_DAYS=60

# TAN Handler
TAN_TIMEOUT_SECONDS=120
TAN_MAX_RETRIES=3
```
