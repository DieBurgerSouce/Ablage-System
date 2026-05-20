# Banking Services - Übersicht

## Ablage-System OCR Platform

**Version**: 1.0
**Erstellt**: 2024-12-18
**Status**: Production

---

## Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│                     Banking Services Layer                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Import Service  │  │ Account Service │  │Transaction Svc  │ │
│  │ (MT940, CSV)    │  │ (CRUD, Balance) │  │ (CRUD, Filter)  │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                     │          │
│           ▼                    ▼                     ▼          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Reconciliation Service                          ││
│  │   (Automatischer Zahlungsabgleich - 5 Matching-Strategien)  ││
│  └─────────────────────────────────────────────────────────────┘│
│           │                    │                     │          │
│           ▼                    ▼                     ▼          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Payment Service │  │ Dunning Service │  │ Cash Flow Svc   │ │
│  │ (SEPA, TAN)     │  │ (Mahnwesen)     │  │ (Forecast)      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│           │                                          │          │
│           ▼                                          ▼          │
│  ┌─────────────────┐                      ┌─────────────────┐  │
│  │TAN Handler Svc  │                      │Aging Report Svc │  │
│  │(photoTAN, push) │                      │(OP-Listen)      │  │
│  └─────────────────┘                      └─────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Service-Übersicht

| Service | Datei | Hauptfunktion |
|---------|-------|---------------|
| **ImportService** | `import_service.py` | Bank-Statement Import (MT940, CSV) |
| **AccountService** | `account_service.py` | Bankkonto-Verwaltung |
| **TransactionService** | `transaction_service.py` | Transaktions-CRUD |
| **ReconciliationService** | `reconciliation_service.py` | Automatischer Zahlungsabgleich |
| **PaymentService** | `payment_service.py` | SEPA-Zahlungsaufträge |
| **DunningService** | `dunning_service.py` | Automatisches Mahnwesen |
| **CashFlowService** | `cash_flow_service.py` | Cashflow-Prognose |
| **AgingReportService** | `aging_report_service.py` | Fälligkeitsberichte |
| **TanHandlerService** | `tan_handler_service.py` | TAN-Authentifizierung |

---

## Kernkonzepte

### 1. Bankkonto-Hierarchie

```
User
 └── BankAccounts (1:n)
      ├── IBAN, BIC, Bank-Name
      ├── Balance, Currency
      └── Transactions (1:n)
           ├── Amount, Date
           ├── Counterparty
           ├── Reference Text
           └── Reconciliation Status
```

### 2. Reconciliation-Status

| Status | Beschreibung |
|--------|--------------|
| `UNMATCHED` | Keine Zuordnung gefunden |
| `MATCHED` | Automatisch oder manuell zugeordnet |
| `PARTIAL` | Teilzahlung (Split-Buchung) |
| `IGNORED` | Vom Benutzer ignoriert |

### 3. Payment-Workflow

```
DRAFT → APPROVED → PENDING_TAN → CONFIRMED
                        │
                        ├── REJECTED (TAN-Fehler)
                        └── CANCELLED (Benutzer-Abbruch)
```

### 4. Dunning-Stufen

| Stufe | Bezeichnung | Tage nach Fälligkeit | Gebühr |
|-------|-------------|---------------------|--------|
| 0 | Nicht begonnen | - | 0 € |
| 1 | Zahlungserinnerung | 7 Tage | 0 € |
| 2 | 1. Mahnung | 14 Tage | 5 € |
| 3 | 2. Mahnung | 28 Tage | 10 € |
| 4 | Letzte Mahnung | 42 Tage | 15 € |

---

## API Endpoints

### Account Management

```
GET    /api/v1/banking/accounts           # Liste Bankkonten
POST   /api/v1/banking/accounts           # Bankkonto anlegen
GET    /api/v1/banking/accounts/{id}      # Bankkonto Details
PUT    /api/v1/banking/accounts/{id}      # Bankkonto aktualisieren
DELETE /api/v1/banking/accounts/{id}      # Bankkonto löschen (soft)
```

### Transactions

```
GET    /api/v1/banking/transactions                    # Liste Transaktionen
GET    /api/v1/banking/transactions/{id}               # Transaktion Details
POST   /api/v1/banking/import/{account_id}             # Import Kontoauszug
GET    /api/v1/banking/accounts/{id}/transactions      # Transaktionen pro Konto
```

### Reconciliation

```
GET    /api/v1/banking/reconciliation/matches/{tx_id}  # Match-Vorschläge
POST   /api/v1/banking/reconciliation/auto             # Auto-Reconciliation
POST   /api/v1/banking/reconciliation/manual           # Manuelles Matching
POST   /api/v1/banking/reconciliation/unmatch          # Match aufheben
POST   /api/v1/banking/reconciliation/split            # Split-Buchung
```

### Payments

```
GET    /api/v1/banking/payments                        # Liste Zahlungen
POST   /api/v1/banking/payments                        # Zahlung erstellen
GET    /api/v1/banking/payments/{id}                   # Zahlung Details
POST   /api/v1/banking/payments/{id}/approve           # Zahlung genehmigen
POST   /api/v1/banking/payments/{id}/submit            # An Bank senden
POST   /api/v1/banking/payments/{id}/confirm           # TAN bestätigen
POST   /api/v1/banking/payments/{id}/cancel            # Zahlung stornieren
GET    /api/v1/banking/payments/skonto                 # Skonto-Möglichkeiten
```

### Dunning

```
GET    /api/v1/banking/dunning                         # Liste Mahnungen
GET    /api/v1/banking/dunning/overdue                 # Überfällige Rechnungen
POST   /api/v1/banking/dunning                         # Mahnung erstellen
POST   /api/v1/banking/dunning/{id}/escalate           # Mahnstufe erhöhen
POST   /api/v1/banking/dunning/{id}/close              # Mahnung abschließen
GET    /api/v1/banking/dunning/stats                   # Mahnstatistiken
POST   /api/v1/banking/dunning/auto                    # Auto-Mahnlauf
```

### Reports

```
GET    /api/v1/banking/cash-flow                       # Cashflow-Prognose
GET    /api/v1/banking/aging-report                    # Fälligkeitsbericht
GET    /api/v1/banking/stats                           # Banking-Statistiken
```

---

## Sicherheit

### Ownership-Validierung

Alle Banking-Services validieren Ownership für:
- Bankkonten (`BankAccount.user_id`)
- Transaktionen (via Bankkonto)
- Dokumente (`Document.owner_id`)
- Zahlungen (via Bankkonto)

```python
# Beispiel: Ownership-Check
account_query = select(BankAccount).where(
    and_(
        BankAccount.id == bank_account_id,
        BankAccount.user_id == user_id,
        BankAccount.deleted_at.is_(None),
    )
)
```

### IBAN/BIC-Validierung

```python
# IBAN-Pattern (ISO 13616)
IBAN_PATTERN = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$"

# Prüfziffer-Validierung (MOD-97)
def _validate_iban_checksum(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1
```

### Betrags-Limits

| Limit | Wert | Zweck |
|-------|------|-------|
| `MAX_SINGLE_PAYMENT` | 50.000 € | Einzelzahlung |
| `MAX_BATCH_TOTAL` | 100.000 € | Sammelzahlung |
| `MIN_DUNNING_AMOUNT` | 5 € | Mindestbetrag für Mahnung |

---

## Parser (Bank-Formate)

Unterstützte Import-Formate:

| Format | Parser | Beschreibung |
|--------|--------|--------------|
| **MT940** | `mt940_parser.py` | SWIFT-Standard |
| **CSV** | `bank_csv/*.py` | Bank-spezifisch |
| **CAMT.053** | `camt_parser.py` | ISO 20022 |

### Bank-spezifische CSV-Parser

| Bank | Datei | Besonderheiten |
|------|-------|----------------|
| DKB | `dkb.py` | Girokonto + Kreditkarte |
| Sparkasse | `sparkasse.py` | CSV mit Semikolon |
| Commerzbank | `commerzbank.py` | UTF-8, Komma-Trennung |
| ING | `ing.py` | PDF-Export-Format |
| N26 | `n26.py` | JSON + CSV |
| Comdirect | `comdirect.py` | Excel + CSV |

---

## Konfiguration

### Dunning-Konfiguration

```python
@dataclass
class DunningConfig:
    # Fristen nach Fälligkeit (Tage)
    reminder_after_days: int = 7
    first_dunning_after_days: int = 14
    second_dunning_after_days: int = 28
    final_dunning_after_days: int = 42

    # Gebühren
    first_dunning_fee: Decimal = Decimal("5.00")
    second_dunning_fee: Decimal = Decimal("10.00")
    final_dunning_fee: Decimal = Decimal("15.00")

    # Verzugszinsen (p.a.)
    late_interest_rate: Decimal = Decimal("5.00")
    base_interest_rate: Decimal = Decimal("3.62")
```

### Reconciliation-Schwellenwerte

```python
class ReconciliationService:
    AUTO_MATCH_THRESHOLD = 0.90   # Ab hier automatisch matchen
    SUGGESTION_THRESHOLD = 0.50   # Ab hier als Vorschlag zeigen
    AMOUNT_TOLERANCE_PERCENT = 0.01  # 1% Betrags-Toleranz
    DATE_TOLERANCE_DAYS = 5       # Tage-Toleranz für Datums-Nähe
```

---

## Datenbank-Modelle

### BankAccount

```sql
CREATE TABLE bank_accounts (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    iban VARCHAR(34) NOT NULL,
    bic VARCHAR(11),
    bank_name VARCHAR(255),
    account_holder VARCHAR(255),
    balance DECIMAL(15,2),
    currency VARCHAR(3) DEFAULT 'EUR',
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    deleted_at TIMESTAMP
);
```

### BankTransaction

```sql
CREATE TABLE bank_transactions (
    id UUID PRIMARY KEY,
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'EUR',
    booking_date DATE NOT NULL,
    value_date DATE,
    counterparty_name VARCHAR(255),
    counterparty_iban VARCHAR(34),
    reference_text TEXT,
    transaction_type VARCHAR(50),
    reconciliation_status VARCHAR(20) DEFAULT 'unmatched',
    matched_document_id UUID REFERENCES documents(id),
    match_confidence DECIMAL(3,2),
    matched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### PaymentOrder

```sql
CREATE TABLE payment_orders (
    id UUID PRIMARY KEY,
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
    batch_id UUID REFERENCES payment_batches(id),
    payment_type VARCHAR(20) DEFAULT 'transfer',
    status VARCHAR(20) DEFAULT 'draft',
    creditor_name VARCHAR(70) NOT NULL,
    creditor_iban VARCHAR(34) NOT NULL,
    creditor_bic VARCHAR(11),
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'EUR',
    reference VARCHAR(140),
    end_to_end_id VARCHAR(35),
    execution_date DATE,
    bank_reference VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    approved_at TIMESTAMP,
    submitted_at TIMESTAMP,
    confirmed_at TIMESTAMP
);
```

### DunningRecord

```sql
CREATE TABLE dunning_records (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    document_id UUID NOT NULL REFERENCES documents(id),
    dunning_level INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    gross_amount DECIMAL(15,2),
    reminder_fee DECIMAL(10,2) DEFAULT 0,
    accrued_interest DECIMAL(10,2) DEFAULT 0,
    due_date DATE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);
```

---

## Metriken

### Prometheus-Metriken

| Metrik | Typ | Beschreibung |
|--------|-----|--------------|
| `banking_transactions_total` | Counter | Importierte Transaktionen |
| `banking_reconciliation_matches` | Counter | Erfolgreiche Matches |
| `banking_reconciliation_confidence` | Histogram | Match-Konfidenz |
| `banking_payments_total` | Counter | Erstellte Zahlungen |
| `banking_dunning_active` | Gauge | Aktive Mahnverfahren |

---

## Weiterführende Dokumentation

- [ReconciliationService.md](./ReconciliationService.md) - Matching-Strategien
- [PaymentService.md](./PaymentService.md) - SEPA & TAN-Workflow
- [DunningService.md](./DunningService.md) - Mahnwesen-Details
- [Parsers.md](./Parsers.md) - Bank-Parser-Formate

---

## Änderungshistorie

| Datum | Version | Änderung | Autor |
|-------|---------|----------|-------|
| 2024-12-18 | 1.0 | Initial Release | Claude Code |
