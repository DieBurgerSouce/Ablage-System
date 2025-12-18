# DunningService - Automatisches Mahnwesen

## Übersicht

Der DunningService verwaltet das automatische Mahnwesen:
- Erkennung überfälliger Rechnungen
- Verwaltung von Mahnstufen
- Berechnung von Mahngebühren und Verzugszinsen
- Automatisierte Mahnläufe

---

## Mahnstufen

```
┌─────────────┐   7 Tage   ┌─────────────┐   14 Tage  ┌─────────────┐
│ FÄLLIG      │───────────▶│ ERINNERUNG  │───────────▶│ 1. MAHNUNG  │
└─────────────┘            └─────────────┘            └─────────────┘
                                                            │
                                                            ▼ 28 Tage
┌─────────────┐   42 Tage  ┌─────────────┐            ┌─────────────┐
│ INKASSO     │◀───────────│ LETZTE      │◀───────────│ 2. MAHNUNG  │
│ (optional)  │            │ MAHNUNG     │            │             │
└─────────────┘            └─────────────┘            └─────────────┘
```

### DunningLevel Enum

| Level | Bezeichnung | Tage nach Fälligkeit | Gebühr |
|-------|-------------|---------------------|--------|
| `NOT_STARTED` | Nicht begonnen | 0 | 0 € |
| `FIRST_REMINDER` | Zahlungserinnerung | 7 | 0 € |
| `SECOND_REMINDER` | 1. Mahnung | 14 | 5 € |
| `FINAL_REMINDER` | 2. Mahnung | 28 | 10 € |
| - | Letzte Mahnung | 42 | 15 € |

### DunningStatus Enum

| Status | Beschreibung |
|--------|--------------|
| `PENDING` | Mahnverfahren aktiv |
| `PAID` | Vollständig bezahlt |
| `PARTIALLY_PAID` | Teilweise bezahlt |
| `WRITTEN_OFF` | Abgeschrieben (uneinbringlich) |
| `CANCELLED` | Storniert |

---

## Konfiguration

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

    # Verzugszinsen (§ 288 BGB)
    late_interest_rate: Decimal = Decimal("5.00")  # 5% über Basiszins
    base_interest_rate: Decimal = Decimal("3.62")  # Aktueller Basiszins

    # Mindestbetrag
    min_dunning_amount: Decimal = Decimal("5.00")
```

---

## API-Operationen

### Überfällige Rechnungen abrufen

```python
async def get_overdue_invoices(
    self,
    db: AsyncSession,
    user_id: UUID,
    min_days_overdue: int = 1,
    max_days_overdue: Optional[int] = None,
    include_in_progress: bool = False,
) -> List[DunningCandidate]:
```

**DunningCandidate**:
```python
@dataclass
class DunningCandidate:
    document_id: UUID
    invoice_number: Optional[str]
    creditor_name: Optional[str]
    amount: Decimal
    due_date: date
    days_overdue: int
    current_level: DunningLevel
    recommended_action: DunningAction
    accumulated_fees: Decimal
    late_interest: Decimal
    total_due: Decimal
```

### Mahnung erstellen

```python
async def create_dunning(
    self,
    db: AsyncSession,
    user_id: UUID,
    document_id: UUID,
    level: DunningLevel,
    notes: Optional[str] = None,
) -> DunningRecordResponse:
```

**Validierungen**:
1. Dokument existiert und gehört User
2. Kein bestehendes Mahnverfahren für dieses Dokument
3. Betrag ≥ `min_dunning_amount`

### Mahnung eskalieren

```python
async def escalate_dunning(
    self,
    db: AsyncSession,
    user_id: UUID,
    dunning_id: UUID,
    notes: Optional[str] = None,
) -> DunningRecordResponse:
```

- Erhöht Mahnstufe um 1
- Addiert neue Gebühr
- Aktualisiert Verzugszinsen

### Mahnung abschließen

```python
async def close_dunning(
    self,
    db: AsyncSession,
    user_id: UUID,
    dunning_id: UUID,
    status: DunningStatus,
    notes: Optional[str] = None,
) -> DunningRecordResponse:
```

**Zulässige Abschluss-Status**:
- `PAID` - Vollständig bezahlt
- `PARTIALLY_PAID` - Teilweise bezahlt
- `WRITTEN_OFF` - Uneinbringlich
- `CANCELLED` - Storniert

### Automatischer Mahnlauf

```python
async def process_automatic_dunning(
    self,
    db: AsyncSession,
    user_id: UUID,
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
```

**dry_run = True**: Nur Simulation, keine Änderungen
**dry_run = False**: Tatsächliche Ausführung

**Response**:
```json
[
  {
    "document_id": "660e8400-e29b-41d4-a716-446655440001",
    "invoice_number": "RE-2024-0042",
    "amount": 1234.56,
    "days_overdue": 21,
    "current_level": "FIRST_REMINDER",
    "recommended_action": "second",
    "executed": true
  }
]
```

---

## Verzugszinsen-Berechnung

### Gesetzliche Grundlage (§ 288 BGB)

- **Verbraucher**: Basiszins + 5%
- **Geschäftskunden**: Basiszins + 9%

### Berechnung

```python
def _calculate_late_interest(
    self,
    principal: Decimal,
    due_date: date,
    as_of_date: date,
) -> Decimal:
    if due_date >= as_of_date:
        return Decimal("0.00")

    days_late = (as_of_date - due_date).days

    # Jahresszins = Basiszins + Aufschlag
    annual_rate = (base_interest_rate + late_interest_rate) / 100

    # Tageszins
    daily_rate = annual_rate / 365

    # Zinsberechnung
    interest = principal * daily_rate * days_late

    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Beispiel**:
```
Rechnungsbetrag: 1.000,00 €
Fällig: 01.12.2024
Heute: 18.12.2024
Tage überfällig: 17

Jahreszins: 3,62% + 5% = 8,62%
Tageszins: 8,62% / 365 = 0,0236%
Verzugszinsen: 1.000 € × 0,0236% × 17 = 4,01 €
```

---

## Mahnstatistiken

```python
async def get_dunning_stats(
    self,
    db: AsyncSession,
    user_id: UUID,
) -> Dict[str, Any]:
```

**Response**:
```json
{
  "overdue": {
    "count": 12,
    "total_amount": 45678.90,
    "total_with_fees": 46123.45
  },
  "active_dunnings": {
    "count": 8,
    "amount": 32100.00
  },
  "by_level": {
    "first_reminder": {"count": 3, "amount": 12000.00},
    "second_reminder": {"count": 4, "amount": 15000.00},
    "final_reminder": {"count": 1, "amount": 5100.00}
  },
  "closed_last_30_days": {
    "paid": 15,
    "partially_paid": 2,
    "written_off": 1
  },
  "fees_collected": 245.00
}
```

---

## DunningAction Enum

```python
class DunningAction(str, Enum):
    REMINDER = "reminder"         # Zahlungserinnerung (gebührenfrei)
    FIRST_DUNNING = "first"       # 1. Mahnung
    SECOND_DUNNING = "second"     # 2. Mahnung
    FINAL_DUNNING = "final"       # Letzte Mahnung
    COLLECTION = "collection"     # Inkasso-Übergabe
    WRITE_OFF = "write_off"       # Forderung abschreiben
```

---

## Workflow: Automatisches Mahnwesen

### 1. Täglicher Mahnlauf (Celery Beat)

```python
# app/workers/tasks/banking_tasks.py

@celery_app.task
async def daily_dunning_check():
    """Täglicher automatischer Mahnlauf."""
    async with get_db_session() as db:
        users = await get_all_users_with_dunning_enabled(db)

        for user in users:
            result = await dunning_service.process_automatic_dunning(
                db, user.id, dry_run=False
            )
            logger.info(
                "daily_dunning_completed",
                user_id=str(user.id),
                actions=len(result),
            )
```

### 2. Manuelle Prüfung

```http
POST /api/v1/banking/dunning/auto?dry_run=true
```

**Response zeigt geplante Aktionen ohne Ausführung**

### 3. Ausführung nach Bestätigung

```http
POST /api/v1/banking/dunning/auto?dry_run=false
```

---

## E-Mail-Integration (optional)

### Mahnschreiben-Versand

```python
async def send_dunning_notice(
    dunning_id: UUID,
    template: str = "default",
) -> bool:
    """Versendet Mahnschreiben per E-Mail."""
    dunning = await get_dunning(dunning_id)

    template_data = {
        "invoice_number": dunning.invoice_number,
        "amount": dunning.gross_amount,
        "fees": dunning.reminder_fee,
        "interest": dunning.accrued_interest,
        "total": dunning.total_outstanding,
        "due_date": dunning.due_date,
        "dunning_level": dunning.dunning_level,
    }

    return await email_service.send(
        to=dunning.debtor_email,
        template=f"dunning_{template}_{dunning.dunning_level}",
        data=template_data,
    )
```

---

## Fehlerbehandlung

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| "Mahnverfahren existiert bereits" | Dokument hat bereits Mahnvorgang | Existierenden Vorgang eskalieren |
| "Mahnvorgang kann nicht eskaliert werden" | Status nicht `PENDING` | Status prüfen, ggf. neu starten |
| "Maximale Mahnstufe bereits erreicht" | Level = FINAL_REMINDER | Inkasso oder Abschreibung |
| "Dokument nicht gefunden" | Falsche ID oder keine Berechtigung | ID und Ownership prüfen |

---

## Best Practices

### 1. Regelmäßige Prüfung

- Täglicher automatischer Mahnlauf (empfohlen: 08:00 Uhr)
- Wöchentliche manuelle Prüfung kritischer Fälle

### 2. Eskalations-Strategie

- Zahlungserinnerung: freundlicher Ton, keine Gebühr
- 1. Mahnung: sachlich, geringe Gebühr
- 2. Mahnung: förmlich, Fristsetzung
- Letzte Mahnung: Inkasso-Androhung

### 3. Ausnahmen dokumentieren

Nutze `notes`-Feld für:
- Vereinbarte Ratenzahlung
- Reklamation des Kunden
- Sonstige Absprachen

### 4. Abschreibung als letzter Ausweg

Vor Abschreibung prüfen:
- Inkasso-Übergabe möglich?
- Rechtliche Schritte sinnvoll?
- Betrag wirtschaftlich verfolgbar?

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
