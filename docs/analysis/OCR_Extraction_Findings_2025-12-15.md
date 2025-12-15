# OCR Extraktion Analyse - Findings Report

**Datum:** 2025-12-15
**Analysierte Dokumente:** 30 (letzte 3 Stunden)
**OCR Backend:** Surya GPU

---

## ZUSAMMENFASSUNG

| Kategorie | Anzahl | Prozent |
|-----------|--------|---------|
| **Korrekt extrahiert** | 9 | 30% |
| **Supplier fehlt** | 15 | 50% |
| **Invoice-Nr fehlt** | 15 | 50% |
| **Invoice-Nr FALSCH** | 5 | 17% |
| **Supplier FALSCH formatiert** | 1 | 3% |

---

## KRITISCHE BUGS

### BUG 1: Invoice-Nummer = Label statt Wert
**Betroffene Dokumente:** 0000000B.TIF, 0000000C.TIF, 0000000D.TIF, 0000000F.TIF
**Symptom:** `invoice_number = "Kunden-Nr"` statt `"246543"`

**OCR-Text zeigt:**
```
Rechnungs-Nr.
Kunden-Nr.
Rechnungsdatum
Rechnung
246543         <- RICHTIGE Rechnungsnummer
25.05.22
310835         <- Kundennummer
```

**Problem:** Das Pattern `(?:rechnungs?-?\s*(?:nr\.?|nummer))` matcht "Rechnungs-Nr." aber nimmt dann "Kunden-Nr" als Wert weil es in der nächsten Zeile steht.

**Root Cause:** Pattern erwartet Wert direkt nach Label, aber bei Tabellen-Layouts stehen Labels und Werte in separaten Spalten/Zeilen.

---

### BUG 2: Invoice-Nummer = "Rechnungsdatum"
**Betroffene Dokumente:** 000000AE.TIF (Amefa)
**Symptom:** `invoice_number = "Rechnungsdatum"` statt `"CD4921000467"`

**OCR-Text zeigt:**
```
Rechnungsnummer
Rechnungsdatum
Kunden Nr.
MwSt Nr.
DE - DEUTSCHLAND
CD4921000467      <- RICHTIGE Rechnungsnummer
13.05.2020
49200974
```

**Problem:** Gleich wie Bug 1 - Tabellen-Layout mit Labels in einer Spalte, Werte in einer anderen.

---

### BUG 3: Supplier ohne Leerzeichen
**Betroffene Dokumente:** 000000AE.TIF
**Symptom:** `supplier = "AmefaStahlwaren"` statt `"Amefa Stahlwaren"`

**Problem:** `_normalize_for_filename()` entfernt alle Leerzeichen, aber der Supplier-Name wird direkt aus dieser Funktion genommen.

---

### BUG 4: Supplier fehlt komplett bei AUER Packaging
**Betroffene Dokumente:** 000000B7.TIF, 000000B4.TIF, 000000B3.TIF, 000000B5.TIF, 000000B6.TIF, 000000B2.TIF

**OCR-Text zeigt:**
```
PACKAGING
AUER Packaging GmbH                <- Supplier klar erkennbar!
Am Kroit 25/27
Technologiepark
83123 AMERANG
```

**Problem:** Firmenname wird nicht extrahiert obwohl "GmbH" Rechtsform vorhanden ist.

**Mögliche Ursache:**
1. `<b>AUER Packaging GmbH</b>` - HTML-Tags stören das Pattern
2. Header ist mehr als 30% des Textes

---

### BUG 5: Invoice-Nr fehlt bei Asal
**Betroffene Dokumente:** 000000B0.TIF

**OCR-Text zeigt:**
```
Rechnung
...
Kunden-Nr.:2073442
RG20012108          <- RICHTIGE Rechnungsnummer!
Bearbeiter: Regina Asal
vom 28.04.2020
```

**Problem:** "RG20012108" wird nicht als Rechnungsnummer erkannt.
**Ursache:** Pattern erwartet "Rechnungsnummer:" Label, aber hier steht nur die Nummer.

---

## WAS FUNKTIONIERT

### Alpac-Rechnungen (Niederländisch)
**Dokumente:** 000000A0-A8.TIF (9 Stück)
**Ergebnis:** Alle korrekt extrahiert!

| File | Supplier | Invoice-Nr |
|------|----------|------------|
| 000000A0.TIF | Alpac | F-201401 |
| 000000A1.TIF | Alpac | F-201384 |
| 000000A2.TIF | Alpac | F-201389 |
| 000000A3.TIF | Alpac | F-201219 |
| 000000A4.TIF | Alpac | F-201315 |
| 000000A5.TIF | Alpac | F-201316 |
| 000000A6.TIF | Alpac | F-201317 |
| 000000A7.TIF | Alpac | F-201342 |
| 000000A8.TIF | Alpac | F-201402 |

**Warum funktioniert es?** Das Format `F-XXXXXX` wird vom Pattern `([A-Z]-?\d{4,8})` direkt erkannt.

---

## DETAILLIERTE BEFUNDE PRO LIEFERANT

### 1. a.b.s. Rechenzentrum (4 Dokumente)
- **Supplier:** `absRechenzentrum` (korrekt, wenn auch ohne Punkte)
- **Invoice-Nr:** `Kunden-Nr` (FALSCH! Sollte 246543 sein)
- **Tatsächliche Rechnungsnummer im OCR:** `246543`

### 2. Amefa Stahlwaren (2 Dokumente)
- **Supplier:** `AmefaStahlwaren` (fehlendes Leerzeichen)
- **Invoice-Nr:** `Rechnungsdatum` (FALSCH! Sollte CD4921002718/CD4921000467 sein)
- **Tatsächliche Rechnungsnummer im OCR:** `CD4921002718`, `CD4921000467`

### 3. AUER Packaging (8 Dokumente)
- **Supplier:** LEER
- **Invoice-Nr:** LEER
- **Tatsächliche Daten im OCR:** Vorhanden aber nicht extrahiert

### 4. Asal (1 Dokument)
- **Supplier:** LEER
- **Invoice-Nr:** LEER
- **Tatsächliche Rechnungsnummer im OCR:** `RG20012108`

### 5. Alpac (9 Dokumente)
- **Supplier:** `Alpac` (KORREKT)
- **Invoice-Nr:** `F-201XXX` (KORREKT)

---

## PATTERN-PROBLEME

### Invoice-Number Patterns
**Aktuelles Pattern:**
```python
r'(?:rechnungs?-?\s*(?:nr\.?|nummer)|rechnung\s*nr\.?)[\s:]*([A-Za-z0-9\-_/]{3,30})'
```

**Problem:** Erwartet Wert direkt nach Label. Bei Tabellen:
```
Label1    Label2    Label3
Wert1     Wert2     Wert3
```
...nimmt es Label2 als Wert von Label1.

**Fehlende Patterns:**
- `RG\d{8}` (Asal-Format)
- `CD\d{10}` (Amefa-Format)
- Standalone-Nummern unter "Rechnung" Header

### Supplier-Name Patterns
**Problem mit HTML-Tags:**
```
<b>AUER Packaging GmbH</b>
```
Pattern `^(.+?(?:GmbH|...))` matcht nicht wegen `<b>` am Anfang.

---

## EMPFOHLENE FIXES (Priorität)

### HIGH - Sofort fixen

1. **HTML-Tags entfernen vor Extraktion**
   ```python
   text = re.sub(r'<[^>]+>', '', text)
   ```

2. **Tabellen-Layout erkennen**
   - Wenn Labels in einer Zeile, Werte in nächster → Spalten-basierte Extraktion

3. **Mehr Invoice-Number Patterns**
   ```python
   r'\bRG\d{8}\b',           # Asal
   r'\bCD\d{10}\b',          # Amefa
   r'\b\d{6}\b(?=\s*\d{2}\.\d{2}\.\d{2})'  # Nummer vor Datum
   ```

### MEDIUM

4. **Supplier-Name mit Leerzeichen behalten**
   - Separate Funktion für Dateiname-Normalisierung vs. Anzeige-Name

5. **Kontext-basierte Extraktion**
   - "Rechnung" Header → nächste alleinstehende Nummer = Rechnungsnummer

### LOW

6. **Confidence-Score pro Feld**
   - Nicht nur Gesamt-Confidence, sondern pro extrahiertem Feld

---

## TEST-FÄLLE FÜR REGRESSION

```python
# Test 1: Tabellen-Layout (a.b.s. Rechenzentrum)
text = """
Rechnungs-Nr.
Kunden-Nr.
Rechnungsdatum
Rechnung
246543
25.05.22
310835
"""
assert extract_invoice_number(text) == "246543"

# Test 2: HTML-Tags (AUER)
text = "<b>AUER Packaging GmbH</b>\nAm Kroit 25/27"
assert extract_supplier_name(text) == "AUER Packaging GmbH"

# Test 3: Amefa-Format
text = "Rechnungsnummer\nCD4921000467"
assert extract_invoice_number(text) == "CD4921000467"

# Test 4: Asal-Format
text = "RG20012108\nBearbeiter: Regina Asal"
assert extract_invoice_number(text) == "RG20012108"
```

---

## STATISTIK

| Lieferant | Dokumente | Supplier OK | Invoice-Nr OK |
|-----------|-----------|-------------|---------------|
| Alpac | 9 | 9 (100%) | 9 (100%) |
| a.b.s. Rechenzentrum | 4 | 4 (100%) | 0 (0%) |
| AUER Packaging | 8 | 0 (0%) | 0 (0%) |
| Amefa | 2 | 2 (100%)* | 0 (0%) |
| Asal | 1 | 0 (0%) | 0 (0%) |
| Unbekannt | 6 | 0 (0%) | 0 (0%) |

*mit Formatierungsfehler (fehlendes Leerzeichen)

---

## FAZIT

Die Extraktion funktioniert **nur für ~30% der Dokumente** korrekt (Alpac).

**Hauptprobleme:**
1. Tabellen-Layouts werden nicht erkannt
2. HTML-Tags stören Pattern-Matching
3. Zu wenig Invoice-Number-Formate unterstützt
4. Keine Fallback-Logik für fehlende Label

**Empfehlung:**
Bevor weitere Dokumente verarbeitet werden, sollten die HIGH-Priority Fixes implementiert werden. Die aktuelle Extraktion ist für Produktionseinsatz nicht geeignet.
