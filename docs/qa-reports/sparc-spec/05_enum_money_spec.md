# 05 — Enum-Drift & Money (Spec)

## TEIL 1: Enum values_callable
### IST (belegt)
**16 Enum-Spalten** ohne `values_callable` und ohne `native_enum=False`. Risiko: SQLAlchemy schreibt den
Member-NAMEN; passt der DB-Enum lowercase-Labels nicht -> `InvalidTextRepresentationError` beim ERSTEN INSERT
(latent, da Tabellen leer). Belegt: `models_team.py:108,138,168,198,228,258,288` (TeamType/Visibility/MemberRole/...),
`models_po_matching.py:145` (MatchStatus), `models_privat_enterprise.py:881` (ApprovalRuleType), `:964` (ApprovalPriority).
**budget (5x)** wurde KORREKT geskippt: DB-Labels dort sind UPPERCASE -> `values_callable` wuerde brechen.

### ZIEL (pro Enum DB-verifiziert, NICHT blind)
Fuer JEDE der 16 Spalten zuerst die DB pruefen, dann entscheiden:
```
labels = psql: SELECT enumlabel FROM pg_enum e JOIN pg_type t ON e.enumtypid=t.oid WHERE t.typname='<dbenum>';
if labels == lowercase(.value):   add values_callable=lambda e: [m.value for m in e]
elif labels == UPPERCASE(.name):  NICHTS aendern (Default ist korrekt)  # wie budget
elif Spalte ist varchar:          optional native_enum=False fuer Konsistenz
else:                             FLAGGEN (Mismatch -> Migration noetig, nicht raten)
```

### TDD-Anker
- `test_<model>_enum_write_read_roundtrip` (Objekt mit jedem Enum-Wert anlegen + zuruecklesen -> kein
  InvalidTextRepresentation; .value stimmt). Pro betroffenem Modell.

### DoD
- [ ] Jede der 16 Spalten: DB-Label-Klasse dokumentiert + Entscheidung (fix/skip/flag) belegt.
- [ ] Roundtrip-Test gruen fuer team/po_matching/approval.
- [ ] budget bleibt unveraendert (Beleg: UPPERCASE).

## TEIL 2: Money-Korrektheit
### IST (belegt)
- **426x `float()`** auf Geldfeldern projektweit (Consumer-Layer + Services). Nur ~5 Dateien wurden auf
  Decimal/ROUND_HALF_UP umgestellt (vat/skonto/partial_payment/insolvency/datev).
- **Wurzel:** Geld-Spalten in `models_entity_business.py` (InvoiceTracking/PaymentTransaction: amount, paid_amount,
  outstanding_amount, skonto_amount, ...) sind `Column(Float)` statt `Numeric(15,2)`. Solange das so ist, rundet
  Postgres bei Persistenz auf Binaer-Float -> Decimal-Disziplin im Code ist nur teilweise wirksam.

### ZIEL
1. **Migration (Wurzel):** Geld-`Float`-Spalten in models_entity_business -> `Numeric(15,2)` (analog models_banking,
   das es bereits korrekt macht). Alembic-Migration + Datenkonvertierung.
2. **Code-Disziplin:** Geldwerte als `Decimal` halten, beim Zuweisen `.quantize(Decimal("0.01"), ROUND_HALF_UP)`;
   `float()` nur fuer Darstellung/JSON, nie als Speicherzwischenschritt.
3. **Invariante:** `net + vat == gross` (exakt) — net zuerst quantisieren, `vat = gross_q - net_q`.

### Pseudocode (Spalte)
```
# vorher
amount = Column(Float)
# nachher (Migration)
amount = Column(Numeric(15, 2))
```

### TDD-Anker
- Property-Test `test_vat_net_plus_vat_equals_gross` (zufaellige gross/rate -> net+vat==gross, ROUND_HALF_UP).
- `test_money_columns_are_numeric` (Reflection: betroffene Spalten sind Numeric, nicht Float).
- `test_invoice_paid_amount_decimal_precision` (Persist+Read behaelt 2 Nachkommastellen exakt).

### DoD
- [ ] Migration vorhanden + `alembic upgrade head` gruen; Spalten Numeric (Reflection-Test).
- [ ] `net+vat==gross`-Property-Test gruen.
- [ ] kein `float(` als Speicher-Zwischenschritt auf Geldpfaden (Review der Top-Services); reine
      Darstellungs-floats erlaubt + dokumentiert.