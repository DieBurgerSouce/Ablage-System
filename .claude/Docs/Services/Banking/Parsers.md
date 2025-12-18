# Banking Parsers - Kontoauszug-Formate

## Übersicht

Die Banking-Parser importieren Kontoauszüge verschiedener Banken und Formate in das Ablage-System.

---

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Import Service                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐              │
│  │ MT940     │  │ CAMT.053  │  │ CSV       │              │
│  │ Parser    │  │ Parser    │  │ Parsers   │              │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘              │
│        │              │              │                     │
│        ▼              ▼              ▼                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │            Base Parser Interface                     │  │
│  │   parse(content) → List[ParsedTransaction]          │  │
│  └─────────────────────────────────────────────────────┘  │
│                          │                                 │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              BankTransaction Model                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Unterstützte Formate

### 1. MT940 (SWIFT-Standard)

**Datei**: `parsers/mt940_parser.py`

| Eigenschaft | Wert |
|-------------|------|
| Standard | SWIFT MT940 |
| Dateierweiterung | `.sta`, `.mt940`, `.txt` |
| Encoding | ISO-8859-1 (Latin-1) |
| Struktur | Tag-basiert (`:20:`, `:61:`, etc.) |

**MT940-Tags**:

| Tag | Beschreibung | Pflicht |
|-----|--------------|---------|
| `:20:` | Transaktions-Referenz | Ja |
| `:25:` | Konto-Identifikation (IBAN) | Ja |
| `:28C:` | Auszugsnummer | Ja |
| `:60F:` | Eröffnungssaldo | Ja |
| `:61:` | Transaktionszeile | Ja |
| `:86:` | Verwendungszweck | Ja |
| `:62F:` | Schlusssaldo | Ja |

**Transaktionszeile (:61:)**:
```
:61:2412181218CR1234,56NTRFNONREF//BANK-REF
     YYMMDD YYMMDD D/C Amount Type Ref // BankRef
```

- `YYMMDD` - Buchungsdatum, Valutadatum
- `D/C` - Debit (D) oder Credit (C)
- `Amount` - Betrag (ohne Währung)
- `Type` - Transaktionstyp (NTRF, NMSC, etc.)

### 2. CAMT.053 (ISO 20022)

**Datei**: `parsers/camt_parser.py`

| Eigenschaft | Wert |
|-------------|------|
| Standard | ISO 20022 |
| Dateierweiterung | `.xml`, `.camt053` |
| Encoding | UTF-8 |
| Struktur | XML |

**XML-Struktur**:
```xml
<Document>
  <BkToCstmrStmt>
    <Stmt>
      <Id>Statement-ID</Id>
      <Acct>
        <Id><IBAN>DE89...</IBAN></Id>
      </Acct>
      <Bal>...</Bal>
      <Ntry>
        <Amt Ccy="EUR">1234.56</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2024-12-18</Dt></BookgDt>
        <NtryDtls>
          <TxDtls>
            <RmtInf><Ustrd>Verwendungszweck</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
```

### 3. Bank-spezifische CSV-Parser

**Verzeichnis**: `parsers/bank_csv/`

---

## CSV-Parser pro Bank

### DKB (Deutsche Kreditbank)

**Datei**: `bank_csv/dkb.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | ISO-8859-1 |
| Trenner | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) |
| Datumsformat | `DD.MM.YYYY` |

**Spalten**:
```
Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;
Verwendungszweck;Kontonummer;BLZ;Betrag (EUR);Gläubiger-ID;
Mandatsreferenz;Kundenreferenz
```

**Besonderheit**: Header beginnt nach Kontoinfo-Block

### Sparkasse

**Datei**: `bank_csv/sparkasse.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | ISO-8859-1 |
| Trenner | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) |
| Datumsformat | `DD.MM.YY` oder `DD.MM.YYYY` |

**Spalten**:
```
Auftragskonto;Buchungstag;Valutadatum;Buchungstext;
Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Kontonummer;
BLZ;Betrag;Waehrung;Info
```

### Commerzbank

**Datei**: `bank_csv/commerzbank.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | UTF-8 |
| Trenner | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) |
| Datumsformat | `DD.MM.YYYY` |

**Spalten**:
```
Buchungstag;Wertstellung;Umsatzart;Buchungstext;Betrag;Währung;
Auftraggeberkonto;Bankleitzahl Auftraggeberkonto;IBAN Auftraggeberkonto
```

### ING

**Datei**: `bank_csv/ing.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | UTF-8 |
| Trenner | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) |
| Datumsformat | `DD.MM.YYYY` |

**Spalten**:
```
Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;
Saldo;Währung;Betrag;Währung
```

### N26

**Datei**: `bank_csv/n26.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | UTF-8 |
| Trenner | Komma (`,`) |
| Dezimaltrennzeichen | Punkt (`.`) |
| Datumsformat | `YYYY-MM-DD` |

**Spalten**:
```
Date,Payee,Account number,Transaction type,Payment reference,
Category,Amount (EUR),Amount (Foreign Currency),
Type Foreign Currency,Exchange Rate
```

### Comdirect

**Datei**: `bank_csv/comdirect.py`

| Eigenschaft | Wert |
|-------------|------|
| Encoding | ISO-8859-1 |
| Trenner | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) |
| Datumsformat | `DD.MM.YYYY` |

---

## Base Parser Interface

```python
# parsers/base.py

from abc import ABC, abstractmethod
from typing import List, Union
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass
class ParsedTransaction:
    """Standardisiertes Transaktions-Format."""
    booking_date: date
    value_date: Optional[date]
    amount: Decimal
    currency: str
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    counterparty_bic: Optional[str]
    reference_text: str
    transaction_type: Optional[str]
    bank_reference: Optional[str]


class BaseBankParser(ABC):
    """Basis-Interface für alle Bank-Parser."""

    @abstractmethod
    def parse(
        self,
        content: Union[str, bytes],
    ) -> List[ParsedTransaction]:
        """Parst Kontoauszug und gibt Transaktionen zurück."""
        pass

    @abstractmethod
    def detect(
        self,
        content: Union[str, bytes],
    ) -> bool:
        """Erkennt ob das Format von diesem Parser unterstützt wird."""
        pass
```

---

## Auto-Detection

```python
# parsers/__init__.py

from typing import List, Union

PARSERS = [
    MT940Parser(),
    CAMTParser(),
    DKBParser(),
    SparkasseParser(),
    CommerzbankParser(),
    INGParser(),
    N26Parser(),
    ComdirectParser(),
]

def auto_detect_and_parse(
    content: Union[str, bytes],
) -> List[ParsedTransaction]:
    """Erkennt Format automatisch und parst."""

    for parser in PARSERS:
        if parser.detect(content):
            return parser.parse(content)

    raise ValueError("Unbekanntes Kontoauszug-Format")
```

---

## Import-Workflow

### 1. Datei-Upload

```http
POST /api/v1/banking/import/{account_id}
Content-Type: multipart/form-data

file: statement.csv
format: auto  # oder "mt940", "camt", "dkb", etc.
```

### 2. Verarbeitung

```python
async def import_statement(
    db: AsyncSession,
    user_id: UUID,
    account_id: UUID,
    file: UploadFile,
    format: str = "auto",
) -> ImportResult:
    # 1. Datei lesen
    content = await file.read()

    # 2. Format erkennen oder verwenden
    if format == "auto":
        transactions = auto_detect_and_parse(content)
    else:
        parser = get_parser(format)
        transactions = parser.parse(content)

    # 3. Duplikate erkennen
    new_transactions = filter_duplicates(db, account_id, transactions)

    # 4. In Datenbank speichern
    saved = await save_transactions(db, account_id, new_transactions)

    return ImportResult(
        total_parsed=len(transactions),
        new_imported=len(saved),
        duplicates_skipped=len(transactions) - len(saved),
    )
```

### 3. Duplikat-Erkennung

```python
def is_duplicate(
    existing: BankTransaction,
    new: ParsedTransaction,
) -> bool:
    """Prüft ob Transaktion bereits existiert."""
    return (
        existing.booking_date == new.booking_date
        and existing.amount == new.amount
        and existing.reference_text == new.reference_text
    )
```

---

## Fehlerbehandlung

### Häufige Parsing-Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `UnicodeDecodeError` | Falsches Encoding | Encoding anpassen |
| `ValueError: Invalid date` | Unbekanntes Datumsformat | Parser-Pattern erweitern |
| `ValueError: Invalid amount` | Zahlenformat | Dezimal-/Tausender-Trenner prüfen |
| "Unbekanntes Format" | Auto-Detection fehlgeschlagen | Format manuell angeben |

### Encoding-Erkennung

```python
import chardet

def detect_encoding(content: bytes) -> str:
    """Erkennt Zeichensatz automatisch."""
    result = chardet.detect(content)
    return result['encoding'] or 'utf-8'
```

---

## Erweiterung: Neuen Parser hinzufügen

### 1. Parser-Klasse erstellen

```python
# parsers/bank_csv/neue_bank.py

from ..base import BaseBankParser, ParsedTransaction

class NeueBankParser(BaseBankParser):
    ENCODING = "utf-8"
    DELIMITER = ";"

    def detect(self, content: Union[str, bytes]) -> bool:
        """Erkennt Neue Bank Format."""
        if isinstance(content, bytes):
            content = content.decode(self.ENCODING, errors='replace')

        # Erste Zeile prüfen
        first_line = content.split('\n')[0]
        return "Neue Bank" in first_line or "NBDE" in first_line

    def parse(self, content: Union[str, bytes]) -> List[ParsedTransaction]:
        """Parst Neue Bank CSV."""
        if isinstance(content, bytes):
            content = content.decode(self.ENCODING)

        transactions = []
        reader = csv.DictReader(
            content.splitlines(),
            delimiter=self.DELIMITER,
        )

        for row in reader:
            tx = ParsedTransaction(
                booking_date=self._parse_date(row["Datum"]),
                amount=self._parse_amount(row["Betrag"]),
                # ... weitere Felder
            )
            transactions.append(tx)

        return transactions
```

### 2. In PARSERS-Liste registrieren

```python
# parsers/__init__.py

from .bank_csv.neue_bank import NeueBankParser

PARSERS = [
    # ... bestehende Parser
    NeueBankParser(),
]
```

### 3. Tests hinzufügen

```python
# tests/unit/services/banking/parsers/test_neue_bank.py

def test_neue_bank_parser_detect():
    parser = NeueBankParser()
    content = "Neue Bank Export\nDatum;Betrag;..."
    assert parser.detect(content) is True

def test_neue_bank_parser_parse():
    parser = NeueBankParser()
    content = "..."
    transactions = parser.parse(content)
    assert len(transactions) == 5
```

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
