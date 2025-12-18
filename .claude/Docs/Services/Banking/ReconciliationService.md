# ReconciliationService - Zahlungsabgleich

## Übersicht

Der ReconciliationService ist das Herzstück des Banking-Moduls. Er gleicht automatisch Banktransaktionen mit Rechnungen (Dokumenten) ab und verwendet dabei 5 verschiedene Matching-Strategien.

---

## Matching-Strategien

### Strategie-Hierarchie (nach Priorität)

| # | Strategie | Konfidenz | Beschreibung |
|---|-----------|-----------|--------------|
| 1 | IBAN + Betrag exakt | 0.99 | Höchste Zuverlässigkeit |
| 2 | Rechnungsnummer + Betrag | 0.95 | Referenz im Verwendungszweck |
| 3 | Kundennummer + Betrag + Datum | 0.85 | Mehrfach-Kriterien |
| 4 | Betrag + Datum-Nähe | 0.75 | Zeitlicher Zusammenhang |
| 5 | Fuzzy Name + Betrag-Toleranz | 0.65 | Fallback-Strategie |

---

## Strategie 1: IBAN + Betrag

**Konfidenz**: 0.99 (exakt) / 0.95 (mit Toleranz)

```python
async def _match_by_iban_amount(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction,
    iban: str,
) -> List[MatchCandidate]:
```

**Ablauf**:
1. Normalisiere IBAN (Leerzeichen entfernen, Uppercase)
2. Suche Rechnungen mit identischer Zahlungs-IBAN
3. Vergleiche Bruttobetrag (exakt oder ±1% Toleranz)

**Beispiel**:
```
Transaktion:
  Counterparty IBAN: DE89370400440532013000
  Betrag: 1.234,56 €

Rechnung:
  Payment Details → IBAN: DE89370400440532013000
  Bruttobetrag: 1.234,56 €

→ Konfidenz: 0.99 (IBAN + Betrag exakt)
```

---

## Strategie 2: Rechnungsnummer + Betrag

**Konfidenz**: 0.95 (exakt) / 0.90 (mit Toleranz)

```python
async def _match_by_invoice_number(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction,
    invoice_numbers: List[str],
) -> List[MatchCandidate]:
```

**Ablauf**:
1. Parse Verwendungszweck mit `reference_parser`
2. Extrahiere Rechnungsnummern (Patterns: RE-, RG-, INV-, etc.)
3. Normalisiere und vergleiche mit Dokumenten-Rechnungsnummern
4. Prüfe Betragsübereinstimmung (±2% Toleranz)

**Reference-Parser Patterns**:
```python
# Erkannte Muster im Verwendungszweck
INVOICE_PATTERNS = [
    r"RE[\-\s]?(\d+)",           # RE-12345, RE 12345
    r"RG[\-\s]?(\d+)",           # RG-12345
    r"INV[\-\s]?(\d+)",          # INV-12345
    r"RECHNUNG[\s:]*(\d+)",      # Rechnung: 12345
    r"(\d{4,})[\s/](\d{4})",     # 12345/2024
]

CUSTOMER_PATTERNS = [
    r"KD[\-\s]?(\d+)",           # KD-12345
    r"KUNDE[\s:]*(\d+)",         # Kunde: 12345
    r"KUNDEN[\-]?NR[\s.:]*(\d+)", # Kunden-Nr.: 12345
]
```

---

## Strategie 3: Kundennummer + Betrag + Datum

**Konfidenz**: 0.80-0.90 (abhängig von Datums-Nähe)

```python
async def _match_by_customer_number(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction,
    customer_numbers: List[str],
) -> List[MatchCandidate]:
```

**Ablauf**:
1. Extrahiere Kundennummern aus Verwendungszweck
2. Suche Rechnungen mit passender Kundennummer
3. Prüfe Betragsübereinstimmung (±2% Toleranz)
4. Berechne Datums-Nähe (Buchungsdatum vs. Fälligkeitsdatum)

**Datums-Nähe Formel**:
```python
days_diff = abs((booking_date - due_date).days)
if days_diff <= DATE_TOLERANCE_DAYS:  # 5 Tage
    date_proximity = 1 - (days_diff / DATE_TOLERANCE_DAYS)
    confidence = 0.80 + (date_proximity * 0.10)
```

---

## Strategie 4: Betrag + Datum-Nähe

**Konfidenz**: 0.70-0.80 (abhängig von Datums-Nähe)

```python
async def _match_by_amount_date(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction,
) -> List[MatchCandidate]:
```

**Ablauf**:
1. Suche Rechnungen mit **exakt** gleichem Bruttobetrag
2. Prüfe Datums-Nähe (max. 5 Tage Differenz)
3. Je näher das Datum, desto höher die Konfidenz

**Wichtig**: Diese Strategie erfordert exakte Betragsübereinstimmung, um False Positives zu minimieren.

---

## Strategie 5: Fuzzy Name-Matching

**Konfidenz**: 0.60-0.75

```python
async def _match_by_fuzzy_name(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction,
) -> List[MatchCandidate]:
```

**Ablauf**:
1. Vergleiche Counterparty-Name mit Absender-Name der Rechnung
2. Berechne Jaccard-Ähnlichkeit (Wort-Überlappung)
3. Prüfe Betragsübereinstimmung (±5% Toleranz)

**Ähnlichkeits-Berechnung**:
```python
def _calculate_name_similarity(name1: str, name2: str) -> float:
    words1 = set(name1.lower().split())
    words2 = set(name2.lower().split())
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)  # Jaccard Index
```

**Beispiel**:
```
Transaktion: "AMAZON EU S.A R.L."
Rechnung:    "Amazon EU S.a r.l., Luxemburg"

Wörter 1: {"amazon", "eu", "s.a", "r.l."}
Wörter 2: {"amazon", "eu", "s.a", "r.l.,", "luxemburg"}
Intersection: 3
Union: 5
Ähnlichkeit: 0.6 → min. 0.7 erforderlich
```

---

## Konfidenz-Schwellenwerte

```python
class ReconciliationService:
    AUTO_MATCH_THRESHOLD = 0.90   # Automatisches Matching
    SUGGESTION_THRESHOLD = 0.50   # Als Vorschlag anzeigen
```

| Konfidenz | Aktion |
|-----------|--------|
| ≥ 0.90 | Automatisch matchen |
| 0.50 - 0.89 | Als Vorschlag anzeigen |
| < 0.50 | Nicht anzeigen |

---

## Batch-Reconciliation

```python
async def batch_reconcile(
    self,
    db: AsyncSession,
    user_id: UUID,
    bank_account_id: Optional[UUID] = None,
    limit: int = 100,
) -> BatchReconciliationResult:
```

**Ablauf**:
1. Hole alle ungematchten Transaktionen (max. `limit`)
2. Für jede Transaktion: `auto_reconcile_transaction()`
3. Zähle Ergebnisse: matched, partial, unmatched

**Ergebnis**:
```python
@dataclass
class BatchReconciliationResult:
    total_processed: int
    matched_count: int
    partial_count: int
    unmatched_count: int
    results: List[ReconciliationResult]
```

---

## Manuelle Operationen

### Manuelles Matching

```python
async def manual_match(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction_id: UUID,
    document_id: UUID,
    notes: Optional[str] = None,
) -> ReconciliationResult:
```

- Setzt `match_confidence = 1.0`
- Setzt `match_method = "manual"`
- Ownership-Validierung für beide Objekte

### Match aufheben

```python
async def unmatch_transaction(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction_id: UUID,
) -> bool:
```

- Setzt Status zurück auf `UNMATCHED`
- Löscht `matched_document_id`, `match_confidence`, `matched_at`

### Split-Buchung (Sammelzahlung)

```python
async def split_transaction(
    self,
    db: AsyncSession,
    user_id: UUID,
    transaction_id: UUID,
    splits: List[Dict[str, Any]],
) -> List[ReconciliationResult]:
```

**Anwendungsfälle**:
- Sammelüberweisung für mehrere Rechnungen
- Teilzahlung einer Rechnung
- Skonto-Abzug

**Validierung**:
1. Summe der Splits = Transaktionsbetrag (±0.01 €)
2. Alle Dokumente müssen dem User gehören

---

## API-Beispiele

### Match-Vorschläge abrufen

```http
GET /api/v1/banking/reconciliation/matches/550e8400-e29b-41d4-a716-446655440000
```

**Response**:
```json
{
  "matches": [
    {
      "document_id": "660e8400-e29b-41d4-a716-446655440001",
      "invoice_number": "RE-2024-0042",
      "gross_amount": 1234.56,
      "confidence": 0.95,
      "match_method": "invoice_number",
      "match_details": {
        "matched_invoice": "2024-0042",
        "doc_invoice": "RE-2024-0042"
      }
    }
  ]
}
```

### Auto-Reconciliation

```http
POST /api/v1/banking/reconciliation/auto
Content-Type: application/json

{
  "bank_account_id": "770e8400-e29b-41d4-a716-446655440000",
  "limit": 50
}
```

**Response**:
```json
{
  "total_processed": 50,
  "matched_count": 32,
  "partial_count": 3,
  "unmatched_count": 15,
  "success_rate": 0.70
}
```

### Split-Buchung

```http
POST /api/v1/banking/reconciliation/split
Content-Type: application/json

{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "splits": [
    {
      "document_id": "660e8400-e29b-41d4-a716-446655440001",
      "amount": 800.00,
      "notes": "Rechnung RE-2024-0042"
    },
    {
      "document_id": "660e8400-e29b-41d4-a716-446655440002",
      "amount": 434.56,
      "notes": "Rechnung RE-2024-0043"
    }
  ]
}
```

---

## Fehlerbehebung

### Niedrige Match-Rate

1. **Prüfen**: Sind Rechnungsnummern in `extracted_data` vorhanden?
2. **Prüfen**: Stimmen IBANs in Zahlungsdetails?
3. **Aktion**: OCR-Qualität für Rechnungen verbessern

### False Positives

1. **Erhöhen**: `AUTO_MATCH_THRESHOLD` (z.B. auf 0.95)
2. **Reduzieren**: `AMOUNT_TOLERANCE_PERCENT` (z.B. auf 0.005)

### Performance bei vielen Transaktionen

1. **Limitieren**: `batch_reconcile(limit=50)` statt 100
2. **Indexe**: Sicherstellen, dass DB-Indexe vorhanden sind
3. **Caching**: Häufig abgefragte Dokumente cachen

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
