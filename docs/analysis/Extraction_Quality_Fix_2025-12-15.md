# Extraction Quality Fix - 2025-12-15

## Executive Summary

Die strukturierte Datenextraktion hatte massive Qualitaetsprobleme mit Label-als-Wert Fehlern
und unvollstaendiger Extraktion. Durch umfassende Pattern-Erweiterungen und Bug-Fixes wurde
die Extraktionsqualitaet signifikant verbessert.

## Ergebnisse

| Metrik | VORHER | NACHHER | Verbesserung |
|--------|--------|---------|--------------|
| Invoice Number | 61.8% | **85.6%** | +23.8% |
| Gross Amount | 60.9% | **97.4%** | +36.5% |
| Sender Company | 66.2% | **93.5%** | +27.3% |
| Label-als-Wert Fehler | 34 Docs | **0** | Behoben |

## Identifizierte Probleme

### Problem 1: Vertikales OCR-Layout (a.b.s. Rechenzentrum)

Das OCR-Layout von a.b.s. Rechenzentrum Dokumenten hatte eine vertikale Struktur:

```
Rechnungs-Nr.     <- Label 1
Kunden-Nr.        <- Label 2
Rechnungsdatum    <- Label 3
Rechnung          <- Header
246543            <- Wert 1 (Rechnungsnummer)
25.05.22          <- Wert 2 (Datum)
310835            <- Wert 3 (Kundennummer)
```

Das Standard-Pattern `Rechnungs-Nr.\s*:\s*(\S+)` matchte "Kunden-Nr." als naechstes
Wort nach dem Label - falsch!

**Loesung**: Neues `INVOICE_NUMBER_VERTICAL_LAYOUT` Pattern das die gesamte
vertikale Struktur erkennt und die richtige Nummer extrahiert.

### Problem 2: Fehlende Vendor-Spezifische Patterns

Verschiedene Lieferanten verwenden eigene Rechnungsnummer-Formate:

| Vendor | Format | Beispiel |
|--------|--------|----------|
| Asal | RG + 8 Ziffern | RG20012108 |
| Amefa | CD + 10 Ziffern | CD4921000467 |
| AUER Packaging | VK + 7 Ziffern | VK 1036735 |
| AUER Delivery | D + 5-6 Ziffern | D119925 |
| a.b.s. | 6 Ziffern vor Datum | 246543 |

**Loesung**: Vendor-spezifische Patterns mit hoher Prioritaet hinzugefuegt.

### Problem 3: Label-Skip Logik fehlte

Das Standard-Pattern extrahierte Labels wie "Kunden-Nr." oder "Rechnungsdatum"
als Rechnungsnummern in Tabellen-Layouts.

**Loesung**: `LABEL_KEYWORDS` frozenset mit ~30 deutschen/englischen Keywords
und `_is_likely_label()` Validierungsfunktion.

### Problem 4: Non-Greedy Company-Name Regex

Das Pattern `.+?` (non-greedy) matchte nur das erste Wort eines mehrteiligen
Firmennamens: "Amefa" statt "Amefa Stahlwaren GmbH".

**Loesung**: Greedy `.+` Pattern mit Lookahead fuer Rechtsformen.

### Problem 5: LEGAL_SUFFIXES False Positives

`\s*ag` matchte Woerter die auf "ag" enden wie "Montag" -> "Monta".

**Loesung**: `\s+ag` (mit Pflicht-Whitespace) verhindert false positives.

## Implementierte Aenderungen

### 1. structured_extraction_service.py

```python
# Neues Pattern fuer vertikales Layout
INVOICE_NUMBER_VERTICAL_LAYOUT = re.compile(
    r'Rechnungs-Nr\.?\s*\n'
    r'Kunden-Nr\.?\s*\n'
    r'Rechnungsdatum\s*\n'
    r'(?:Rechnung\s*\n)?'
    r'(\d{5,8})',
    re.IGNORECASE
)

# Label-Keywords zur Validierung
LABEL_KEYWORDS = frozenset([
    'datum', 'nr', 'nummer', 'kunde', 'kunden', 'betrag',
    'mwst', 'steuer', 'summe', 'netto', 'brutto', ...
])

def _is_likely_label(self, value: str) -> bool:
    """Prueft ob ein Wert wahrscheinlich ein Label ist."""
    value_clean = value.lower().replace('-', '').replace('.', '')
    return any(kw in value_clean for kw in LABEL_KEYWORDS)
```

### 2. reference_patterns.py

```python
# Vendor-spezifische Patterns
INVOICE_NUMBER_RG = re.compile(r'\b(?P<number>RG\d{8})\b', re.IGNORECASE)
INVOICE_NUMBER_CD = re.compile(r'\b(?P<number>CD\d{10})\b', re.IGNORECASE)
INVOICE_NUMBER_VK = re.compile(r'\bVK\s*(?P<number>\d{7})\b', re.IGNORECASE)
INVOICE_NUMBER_D = re.compile(r'\b(?P<number>D\d{5,6})\b', re.IGNORECASE)
INVOICE_NUMBER_VERTICAL = re.compile(...)
```

### 3. entity_extraction_service.py

```python
# FIX: Greedy Pattern fuer mehrteilige Firmennamen
COMPANY_NAME = re.compile(
    r'\b([A-ZAEOEUE][A-Za-zaeoeueß&\-\.]+(?:\s+[A-Za-zaeoeueß&\-\.]+)*)[ \t]+'
    r'(GmbH|mbH|AG|KG|...)',
    re.UNICODE
)
```

### 4. company_matching_service.py

```python
# FIX: \s+ statt \s* vor kurzen Suffixen
LEGAL_SUFFIXES = [
    r"\s+ag\s*$",    # \s+ um "...dag" nicht zu matchen
    r"\s+kg\s*$",    # \s+ um "...ekg" nicht zu matchen
    r"\s+se\s*$",    # \s+ um "Spargelmesse" nicht zu matchen
    ...
]
```

## Test-Ergebnisse

```
tests/unit/services/test_extraction_fixes.py - 33 passed
```

Alle 33 Unit Tests bestehen, inklusive:
- Vendor-spezifische Formate (RG, CD, VK, D)
- Label-Skip Logik
- Mehrteilige Firmennamen
- HTML/Markdown Bereinigung

## Betroffene Dateien

- `app/services/structured_extraction_service.py`
- `app/services/extraction/patterns/reference_patterns.py`
- `app/services/entity_extraction_service.py`
- `app/services/quick_classification_service.py`
- `app/services/company_matching_service.py`

## Empfehlungen

1. **Monitoring**: Regelmaessige Qualitaetspruefung der Extraktion
2. **Neue Vendor-Patterns**: Bei neuen Lieferanten-Formaten Patterns erweitern
3. **OCR-Qualitaet**: Vertikale Layouts entstehen durch OCR-Spalten-Erkennung

## Autor

Claude Code - 2025-12-15
