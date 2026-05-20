# Kasse-Modul Implementierung

## Auftrag

Implementiere das vollständige **Kasse-Modul** für das Ablage-System gemäß der Spezifikation in `.claude/commands/implement-kasse-module.md`.

Das Modul umfasst:
- **Multi-Company Architektur** mit PostgreSQL Row-Level Security
- **Kassenbuchführung** (GoBD-konform, APPEND-ONLY!)
- **Spesenabrechnung** mit Bewirtungskosten-Dokumentation
- **Kassensturz** (Zählprotokoll)
- **Banking-Integration** für Entnahmen/Einlagen
- **OCR-Integration** für automatische Belegerkennung

---

## KRITISCHE REGELN (NICHT VERHANDELBAR!)

### GoBD-Compliance
```
⚠️ CashEntry ist APPEND-ONLY - KEINE Updates, KEINE Deletes!
⚠️ Stornierung NUR durch Gegenbuchung mit Verweis auf Original
⚠️ entry_date darf NICHT in der Zukunft liegen
⚠️ entry_number ist fortlaufend pro Kasse/Jahr - KEINE Lücken!
⚠️ balance_after muss bei JEDER Buchung korrekt berechnet werden
```

### Projekt-Standards
```
✓ Deutsche Texte für alle Fehlermeldungen und UI
✓ Type Hints bei ALLEN Funktionen (Python + TypeScript)
✓ JSDoc-Kommentare auf Deutsch
✓ Pydantic v2 für alle Schemas
✓ React Query mit STALE_TIMES Pattern
✓ shadcn/ui Komponenten
```

---

## IMPLEMENTIERUNGS-REIHENFOLGE

### Phase 1: Multi-Company Foundation
```
1. Alembic Migration: companies + user_companies Tabellen
2. SQLAlchemy Models: Company, UserCompany
3. Company Context Middleware (RLS)
4. API Endpoints: /api/v1/companies
5. Frontend: Company Switcher Komponente
6. Migration: CompanySettings -> Company
```

### Phase 2: Kassenbuch Core
```
1. Alembic Migration: cash_registers, cash_entries, cash_categories, cash_counts
2. SQLAlchemy Models mit allen Constraints
3. CashService mit Transaktionslogik
4. API Endpoints: /api/v1/cash/*
5. Seed: Default-Kategorien (SKR03/SKR04)
```

### Phase 3: Spesenabrechnung
```
1. Alembic Migration: expense_reports, expense_items
2. SQLAlchemy Models
3. ExpenseService mit Workflow-Logik
4. API Endpoints: /api/v1/expenses/*
5. Verpflegungspauschalen-Berechnung
```

### Phase 4: Frontend
```
1. TypeScript Types (cash.ts)
2. API Hooks (useCashRegisters, useCashEntries, etc.)
3. Kassenbuch-Dashboard
4. Kasseneintrag-Formular (mit Bewirtungs-Modus)
5. Kassensturz-Dialog
6. Spesenabrechnung-Wizard
```

### Phase 5: Integration
```
1. OCR: Receipt-Erkennung erweitern
2. Banking: Kassenentnahme/-einlage Verknüpfung
3. DATEV: Export-Erweiterung für Kassenbuchungen
```

---

## DATEIEN ZUM ERSTELLEN

### Backend (Python)
```
alembic/versions/XXXX_add_multi_company.py
alembic/versions/XXXX_add_cash_module.py
alembic/versions/XXXX_add_expense_module.py

app/db/models/company.py
app/db/models/cash.py
app/db/models/cash_enums.py
app/db/models/expense.py

app/schemas/company.py
app/schemas/cash.py
app/schemas/expense.py

app/services/cash.py
app/services/expense.py

app/api/v1/companies.py
app/api/v1/cash.py
app/api/v1/expenses.py

app/middleware/company_context.py
```

### Frontend (TypeScript/React)
```
frontend/src/types/models/cash.ts
frontend/src/types/models/company.ts

frontend/src/api/companies.ts
frontend/src/api/cash.ts
frontend/src/api/expenses.ts

frontend/src/hooks/useCompanies.ts
frontend/src/hooks/useCash.ts
frontend/src/hooks/useExpenses.ts

frontend/src/features/cash/
  ├── components/
  │   ├── CashRegisterList.tsx
  │   ├── CashEntryForm.tsx
  │   ├── CashEntryList.tsx
  │   ├── CashCountDialog.tsx
  │   ├── EntertainmentFields.tsx
  │   └── CashBookSummary.tsx
  ├── pages/
  │   ├── CashDashboard.tsx
  │   └── CashBookPage.tsx
  └── index.ts

frontend/src/features/expenses/
  ├── components/
  │   ├── ExpenseReportList.tsx
  │   ├── ExpenseReportForm.tsx
  │   ├── ExpenseItemForm.tsx
  │   ├── MileageCalculator.tsx
  │   ├── PerDiemCalculator.tsx
  │   └── ExpenseWorkflow.tsx
  ├── pages/
  │   └── ExpensesPage.tsx
  └── index.ts

frontend/src/components/company/
  ├── CompanySwitcher.tsx
  └── CompanySelector.tsx
```

---

## REFERENZ-PATTERNS

### Existing Banking Module (als Vorlage)
```
app/api/v1/banking.py          # 2756 Zeilen - API Pattern
app/services/banking/          # Service-Struktur
frontend/src/features/banking/ # Feature-Struktur
frontend/src/types/models/banking.ts # Type Pattern
```

### Existing Mahnwesen (Workflow-Pattern)
```
app/db/models.py:3200+         # DunningProcess, DunningStep
app/services/dunning.py        # Workflow-Service
```

---

## SPEZIFISCHE IMPLEMENTIERUNGS-DETAILS

### CashService.create_entry() - Kernlogik
```python
async def create_entry(self, company_id, user_id, data):
    # 1. Kasse laden & Sperre
    register = await self._get_register_for_update(data.cash_register_id)
    
    # 2. Nächste Nummer ermitteln
    fiscal_year = data.entry_date.year
    next_number = await self._get_next_entry_number(
        register.id, fiscal_year
    )
    
    # 3. Neuen Saldo berechnen
    new_balance = register.current_balance + data.amount
    
    # 4. Steuerberechnung
    tax_info = self._calculate_tax(data)
    
    # 5. Buchungskonto ermitteln
    accounts = self._get_accounts(data.entry_type, data.category_id)
    
    # 6. Entry erstellen (APPEND-ONLY!)
    entry = CashEntry(
        company_id=company_id,
        cash_register_id=register.id,
        entry_number=next_number,
        fiscal_year=fiscal_year,
        entry_date=data.entry_date,
        value_date=data.value_date or data.entry_date,
        amount=data.amount,
        balance_after=new_balance,
        entry_type=data.entry_type,
        # ... rest
        created_by_id=user_id
    )
    
    # 7. Kasse aktualisieren
    register.current_balance = new_balance
    register.balance_date = datetime.now()
    
    # 8. Commit
    self.db.add(entry)
    await self.db.commit()
    
    return entry
```

### Verpflegungspauschale-Berechnung
```python
def calculate_per_diem(
    hours: float,
    breakfast_provided: bool = False,
    lunch_provided: bool = False,
    dinner_provided: bool = False
) -> Decimal:
    """Berechnet Verpflegungspauschale nach §9 Abs. 4a EStG."""
    
    if hours < 8:
        base = Decimal("0")
    elif hours < 24:
        base = Decimal("14")  # >8h
    else:
        base = Decimal("28")  # 24h
    
    # Kürzungen bei Mahlzeitengestellung
    if breakfast_provided:
        base -= Decimal("5.60")  # 20% von 28€
    if lunch_provided:
        base -= Decimal("11.20")  # 40% von 28€
    if dinner_provided:
        base -= Decimal("11.20")  # 40% von 28€
    
    return max(base, Decimal("0"))
```

### Bewirtungskosten-Validierung
```python
def validate_entertainment(data: EntertainmentData) -> list[str]:
    """Validiert Bewirtungskosten-Angaben."""
    errors = []
    
    if not data.participants or len(data.participants) == 0:
        errors.append("Teilnehmer müssen namentlich genannt werden")
    
    if not data.occasion:
        errors.append("Anlass muss angegeben werden")
    
    # Prüfung auf ungültige Anlässe
    invalid_occasions = ["geschäftsessen", "kundenpflege", "meeting"]
    if data.occasion.lower() in invalid_occasions:
        errors.append(
            "Anlass zu unkonkret. Bitte spezifischen Grund angeben "
            "(z.B. 'Abstimmung Lieferbedingungen Projekt ABC')"
        )
    
    return errors
```

---

## TESTS

### Unit Tests
```
tests/unit/services/test_cash_service.py
tests/unit/services/test_expense_service.py
tests/unit/models/test_cash_models.py
```

### Integration Tests
```
tests/integration/api/test_cash_api.py
tests/integration/api/test_expense_api.py
tests/integration/api/test_company_api.py
```

### E2E Tests
```
frontend/e2e/cash-book.spec.ts
frontend/e2e/expense-report.spec.ts
```

---

## NACH IMPLEMENTIERUNG

1. **Migrations ausführen**: `alembic upgrade head`
2. **Seed-Daten laden**: Default-Kategorien
3. **Tests ausführen**: `pytest tests/ -v --cov=app`
4. **Frontend testen**: `npm run test`
5. **Lint**: `ruff check app/` + `npm run lint`
6. **CLAUDE.md aktualisieren**: Neue Endpoints dokumentieren

---

## FRAGEN VOR START

Bevor du beginnst, lies die vollständige Spezifikation in `.claude/commands/implement-kasse-module.md` und bestätige:

1. Hast du die GoBD-Anforderungen verstanden (APPEND-ONLY, keine Zukunftsbuchungen)?
2. Verstehst du das Multi-Company RLS-Pattern?
3. Ist die Bewirtungskosten-70/30-Logik klar?
4. Kennst du die SKR03/SKR04 Kontenzuordnungen?

Starte mit **Phase 1: Multi-Company Foundation**.
