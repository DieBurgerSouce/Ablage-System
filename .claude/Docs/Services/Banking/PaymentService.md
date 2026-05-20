# PaymentService - SEPA-Zahlungsaufträge

## Übersicht

Der PaymentService verwaltet SEPA-Zahlungsaufträge mit vollständigem TAN-Workflow:
- Einzelüberweisungen (PAIN.001)
- Lastschriften (PAIN.008)
- Sammelzahlungen (Batches)
- Skonto-Erkennung

---

## Payment-Workflow

```
┌─────────┐     ┌──────────┐     ┌─────────────┐     ┌───────────┐
│  DRAFT  │────▶│ APPROVED │────▶│ PENDING_TAN │────▶│ CONFIRMED │
└─────────┘     └──────────┘     └─────────────┘     └───────────┘
                      │                 │
                      ▼                 ▼
                ┌───────────┐    ┌───────────┐
                │ CANCELLED │    │ REJECTED  │
                └───────────┘    └───────────┘
```

### Status-Beschreibung

| Status | Beschreibung | Nächste Aktion |
|--------|--------------|----------------|
| `DRAFT` | Entwurf erstellt | Genehmigen |
| `APPROVED` | Genehmigt, bereit zum Senden | An Bank senden |
| `PENDING_TAN` | Wartet auf TAN-Eingabe | TAN eingeben |
| `CONFIRMED` | Von Bank bestätigt | ✓ Abgeschlossen |
| `REJECTED` | Abgelehnt (TAN-Fehler) | Neu versuchen |
| `CANCELLED` | Storniert | - |

---

## Zahlungsarten

### PaymentType Enum

```python
class PaymentType(str, Enum):
    TRANSFER = "transfer"        # Überweisung (PAIN.001)
    DIRECT_DEBIT = "direct_debit"  # Lastschrift (PAIN.008)
    STANDING_ORDER = "standing_order"  # Dauerauftrag
```

---

## API-Operationen

### Zahlung erstellen

```python
async def create_payment(
    self,
    db: AsyncSession,
    user_id: UUID,
    bank_account_id: UUID,
    data: PaymentOrderCreate,
) -> PaymentOrderResponse:
```

**Validierungen**:
1. Bankkonto-Ownership
2. Optional: `linked_document_id` Ownership
3. Optional: `linked_transaction_id` Ownership
4. IBAN-Format und Prüfziffer
5. BIC-Format (optional)
6. Betrag > 0 und < MAX_SINGLE_PAYMENT
7. Empfängername 2-70 Zeichen
8. Verwendungszweck max. 140 Zeichen
9. Ausführungsdatum nicht in Vergangenheit

**Request**:
```json
{
  "bank_account_id": "550e8400-e29b-41d4-a716-446655440000",
  "creditor_name": "Max Mustermann GmbH",
  "creditor_iban": "DE89370400440532013000",
  "creditor_bic": "COBADEFFXXX",
  "amount": 1234.56,
  "currency": "EUR",
  "reference": "Rechnung RE-2024-0042",
  "execution_date": "2024-12-20",
  "urgent": false,
  "linked_document_id": "660e8400-e29b-41d4-a716-446655440001"
}
```

### Zahlung genehmigen

```python
async def approve_payment(
    self,
    db: AsyncSession,
    user_id: UUID,
    payment_id: UUID,
) -> PaymentOrderResponse:
```

- Nur von `DRAFT` → `APPROVED`
- Setzt `approved_at` Timestamp

### An Bank senden

```python
async def submit_payment(
    self,
    db: AsyncSession,
    user_id: UUID,
    payment_id: UUID,
) -> Dict[str, Any]:
```

- Nur von `APPROVED` → `PENDING_TAN`
- Generiert TAN-Challenge

**TAN-Challenge Response**:
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "challenge_type": "photoTAN",
  "challenge_data": "base64-encoded-qr-code",
  "expires_at": "2024-12-18T15:05:00Z",
  "tan_required": true
}
```

### TAN bestätigen

```python
async def confirm_with_tan(
    self,
    db: AsyncSession,
    user_id: UUID,
    payment_id: UUID,
    tan: str,
) -> PaymentOrderResponse:
```

- Max. 3 TAN-Versuche
- Bei Erfolg: `CONFIRMED` + `bank_reference`
- Bei Fehler nach 3 Versuchen: `REJECTED`

### Zahlung stornieren

```python
async def cancel_payment(
    self,
    db: AsyncSession,
    user_id: UUID,
    payment_id: UUID,
    reason: Optional[str] = None,
) -> PaymentOrderResponse:
```

- Nur von: `DRAFT`, `APPROVED`, `PENDING_TAN`
- Nicht mehr stornierbar: `CONFIRMED`, `REJECTED`

---

## Sammelzahlungen (Batches)

### Batch erstellen

```python
async def create_batch(
    self,
    db: AsyncSession,
    user_id: UUID,
    bank_account_id: UUID,
    name: str,
    payments: List[PaymentOrderCreate],
) -> Dict[str, Any]:
```

**Validierungen**:
1. Alle Einzelzahlungen validieren
2. Gesamtbetrag ≤ MAX_BATCH_TOTAL (100.000 €)
3. Einheitliche Währung

**Response**:
```json
{
  "batch_id": "880e8400-e29b-41d4-a716-446655440000",
  "name": "Lieferantenrechnungen Dezember",
  "payment_count": 15,
  "total_amount": 45678.90,
  "status": "draft",
  "payments": ["uuid1", "uuid2", "..."]
}
```

---

## Skonto-Erkennung

### Skonto-Möglichkeiten abrufen

```python
async def get_skonto_opportunities(
    self,
    db: AsyncSession,
    user_id: UUID,
    days_ahead: int = 14,
) -> List[Dict[str, Any]]:
```

Findet Rechnungen mit Skonto-Konditionen, die in den nächsten `days_ahead` Tagen ablaufen.

**Response**:
```json
[
  {
    "document_id": "660e8400-e29b-41d4-a716-446655440001",
    "invoice_number": "RE-2024-0042",
    "creditor_name": "Lieferant GmbH",
    "gross_amount": 5000.00,
    "skonto_percent": 3.0,
    "skonto_date": "2024-12-22",
    "days_remaining": 4,
    "potential_savings": 150.00,
    "discounted_amount": 4850.00
  }
]
```

**Sortierung**: Nach `days_remaining` (dringlichste zuerst)

---

## IBAN-Validierung

### Format-Validierung

```python
IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")
```

### Prüfziffer-Validierung (MOD-97)

```python
def _validate_iban_checksum(self, iban: str) -> bool:
    # 1. Erste 4 Zeichen ans Ende verschieben
    rearranged = iban[4:] + iban[:4]

    # 2. Buchstaben in Zahlen umwandeln (A=10, B=11, ...)
    numeric = ""
    for char in rearranged:
        if char.isalpha():
            numeric += str(ord(char) - 55)
        else:
            numeric += char

    # 3. MOD 97 = 1
    return int(numeric) % 97 == 1
```

**Beispiel**:
```
IBAN: DE89370400440532013000
Rearranged: 370400440532013000DE89
D=13, E=14: 370400440532013000131489
371319898 % 97 = 1 ✓
```

---

## Limits und Constraints

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `MAX_SINGLE_PAYMENT` | 50.000 € | Max. Einzelzahlung |
| `MAX_BATCH_TOTAL` | 100.000 € | Max. Sammelzahlung |
| `TAN_MAX_ATTEMPTS` | 3 | Max. TAN-Versuche |
| `TAN_EXPIRY` | 5 Minuten | TAN-Challenge Gültigkeit |
| `IBAN_MAX_LENGTH` | 34 Zeichen | ISO 13616 |
| `REFERENCE_MAX_LENGTH` | 140 Zeichen | SEPA-Limit |
| `CREDITOR_NAME_MAX` | 70 Zeichen | SEPA-Limit |

---

## End-to-End-ID

Eindeutige Kennung für Zahlungsverfolgung (SEPA-Standard):

```python
def _generate_end_to_end_id(self) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unique = str(uuid4())[:8].upper()
    return f"E2E{timestamp}{unique}"
    # Beispiel: E2E20241218143022A1B2C3D4
```

---

## Fehlerbehandlung

### ValidationError

```python
class PaymentValidationResult:
    valid: bool
    errors: List[str]    # Kritische Fehler
    warnings: List[str]  # Warnungen (Betrag hoch, etc.)
```

### Häufige Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| "Ungültige IBAN" | Format oder Prüfziffer falsch | IBAN korrigieren |
| "Betrag muss positiv sein" | Negativer oder 0-Betrag | Positiven Betrag eingeben |
| "Empfängername zu lang" | > 70 Zeichen | Kürzen |
| "Verwendungszweck zu lang" | > 140 Zeichen | Kürzen |
| "Maximale TAN-Versuche überschritten" | 3x falsche TAN | Neue Zahlung erstellen |

---

## Sicherheit

### Ownership-Validierung

Jede Operation validiert:
1. Bankkonto gehört User
2. Verknüpfte Dokumente gehören User
3. Verknüpfte Transaktionen gehören User (via Bankkonto)

### Logging

Alle kritischen Operationen werden geloggt:
```python
logger.info(
    "payment_confirmed",
    payment_id=str(payment_id),
    bank_reference=payment.bank_reference,
)
```

Sensible Daten (TAN, volle IBAN) werden **nicht** geloggt.

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
