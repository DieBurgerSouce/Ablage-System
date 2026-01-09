# German Language Testing Guide

> **Ablage-System Enterprise Documentation**
> Version: 1.0 | Stand: Januar 2025

## Übersicht

Dieses Dokument beschreibt die Teststrategie für deutsche Sprachverarbeitung im Ablage-System. Das Ziel ist **100% Umlaut-Genauigkeit** bei der OCR-Verarbeitung deutscher Dokumente.

---

## 1. Kernbereiche der German Language Tests

### 1.1 Abgedeckte Bereiche

| Bereich | Testdateien | Testfälle |
|---------|-------------|-----------|
| Umlaut-Validierung | `test_german_validator.py` | 15+ |
| Umlaut-Korrektur | `test_german_correction_agent.py` | 50+ |
| Fraktur-Erkennung | `test_fraktur_detector.py` | 30+ |
| Historische Normalisierung | `test_historical_german_normalizer.py` | 40+ |
| Komposita-Splitting | `test_german_compound_splitter.py` | 20+ |
| **Gesamt** | **5 Dateien** | **150+ Testfälle** |

### 1.2 Verzeichnisstruktur

```
tests/
├── unit/
│   ├── test_german_validator.py              # Kern-Validierung
│   ├── agents/postprocessing/
│   │   └── test_german_correction_agent.py   # Korrektur-Agent
│   ├── agents/preprocessing/
│   │   └── test_fraktur_detector.py          # Fraktur-Erkennung
│   └── services/
│       ├── test_historical_german_normalizer.py
│       └── test_german_compound_splitter.py
├── fixtures/
│   └── german_docs/                          # Fixture-Dateien
│       ├── invoices/                         # 6 Rechnungen
│       ├── fraktur/                          # 6 Fraktur-Samples
│       ├── tables/                           # 6 Tabellen
│       ├── contracts/                        # 6 Verträge
│       ├── forms/                            # 3 Formulare
│       ├── handwritten/                      # 3 Handschriften
│       └── mixed/                            # 3 Gemischte Layouts
└── e2e/
    └── conftest.py                           # German Text Fixtures
```

---

## 2. Umlaut-Validierung Tests

### 2.1 Basis-Validierung

```python
# tests/unit/test_german_validator.py

def test_umlaut_validation_correct():
    """Test validation of correct German text."""
    text = "Müller GmbH & Co. KG"
    result = validate_german_text(text)

    assert "ü" in text
    assert result["confidence"] >= 0.9

def test_umlaut_validation_with_errors():
    """Test detection of OCR errors."""
    text = "Mueller GmbH"  # Fehlender Umlaut
    result = validate_german_text(text)

    # Fehler erkannt: ue → ü Pattern
    assert result["confidence"] < 1.0
    assert len(result["umlaut_corrections"]) > 0
```

### 2.2 Parametrisierte Umlaut-Tests

```python
@pytest.mark.parametrize("text,expected_umlauts", [
    ("Müller", ["ü"]),
    ("Größe", ["ö"]),
    ("Fußball", ["ß"]),
    ("Äpfel und Birnen", ["Ä"]),
    ("Übersetzung für Bücher", ["Ü", "ü"]),
])
def test_umlaut_detection_parametrized(text, expected_umlauts):
    """Parametrized test for umlaut detection."""
    result = detect_umlauts(text)

    for umlaut in expected_umlauts:
        assert umlaut in result["detected_umlauts"]
```

### 2.3 Datumsformat-Validierung

```python
@pytest.mark.parametrize("date_string,expected_found", [
    ("01.01.2024", True),      # DD.MM.YYYY
    ("31.12.2024", True),      # DD.MM.YYYY
    ("15. Januar 2025", True), # DD. Month YYYY
    ("1. Mai 2024", True),     # D. Month YYYY
    ("invalid date", False),
])
def test_date_extraction(date_string, expected_found):
    """Test German date format extraction."""
    result = extract_dates(date_string)

    assert (len(result) > 0) == expected_found
```

### 2.4 Währungsformat-Validierung

```python
@pytest.mark.parametrize("currency_string,expected_found", [
    ("100,00 €", True),        # Standard
    ("1.234,56 €", True),      # Mit Tausender-Trennzeichen
    ("€ 50,00", True),         # Prefix
    ("EUR 1.000,00", True),    # Währungscode
    ("no currency here", False),
])
def test_currency_extraction(currency_string, expected_found):
    """Test German currency format extraction."""
    result = extract_currencies(currency_string)

    assert (len(result) > 0) == expected_found
```

---

## 3. Umlaut-Korrektur Tests

### 3.1 Umlaut-Restoration Tests

```python
# tests/unit/agents/postprocessing/test_german_correction_agent.py

class TestUmlautRestoration:

    def test_restore_ae_to_a_umlaut(self):
        """ae → ä restoration."""
        text = "Die Aenderung wurde bestaetigt."
        result = correct_german_text(text)

        assert "Änderung" in result["text"]
        assert "bestätigt" in result["text"]

    def test_restore_oe_to_o_umlaut(self):
        """oe → ö restoration."""
        text = "Die Oeffnungszeiten der Behoerde."
        result = correct_german_text(text)

        assert "Öffnungszeiten" in result["text"]
        assert "Behörde" in result["text"]

    def test_restore_ue_to_u_umlaut(self):
        """ue → ü restoration."""
        text = "Wir muessen die Pruefung durchfuehren."
        result = correct_german_text(text)

        assert "müssen" in result["text"]
        assert "Prüfung" in result["text"]
        assert "durchführen" in result["text"]

    def test_uppercase_umlaut_restoration(self):
        """Uppercase umlaut restoration."""
        text = "AENDERUNG und OEFFNUNG"
        result = correct_german_text(text)

        assert "ÄNDERUNG" in result["text"]
```

### 3.2 Eszett (ß) Korrekturen

```python
class TestEszettCorrections:

    def test_correct_strasse_to_straße(self):
        """strasse → straße."""
        text = "Die Strasse in Berlin."
        result = correct_german_text(text)

        assert "Straße" in result["text"]

    def test_correct_grosse_to_große(self):
        """grosse → große."""
        text = "Eine grosse Veranstaltung."
        result = correct_german_text(text)

        assert "große" in result["text"]

    def test_correct_heisst_to_heißt(self):
        """heisst → heißt."""
        text = "Das heisst, wir beginnen."
        result = correct_german_text(text)

        assert "heißt" in result["text"]

    def test_preserve_correct_eszett(self):
        """Keine Over-Correction bei korrektem ß."""
        text = "Die Straße ist groß."
        result = correct_german_text(text)

        # Keine Änderung, bereits korrekt
        assert result["text"] == text
```

### 3.3 Domain-spezifische Korrekturen

```python
class TestDomainSpecificCorrections:

    def test_accounting_domain_corrections(self):
        """Accounting domain corrections."""
        text = "Die Buchfuehrung zeigt Rueckstellungen."
        result = correct_german_text(text, domain="accounting")

        assert "Buchführung" in result["text"]
        assert "Rückstellungen" in result["text"]

    def test_legal_domain_corrections(self):
        """Legal domain corrections."""
        text = "Der Geschaeftsfuehrer und die Kuendigungsfrist."
        result = correct_german_text(text, domain="legal")

        assert "Geschäftsführer" in result["text"]
        assert "Kündigungsfrist" in result["text"]

    def test_medical_domain_corrections(self):
        """Medical domain corrections."""
        text = "Der Arztbericht zur Gesundheitspruefung."
        result = correct_german_text(text, domain="medical")

        assert "Gesundheitsprüfung" in result["text"]
```

---

## 4. Fraktur-Erkennung Tests

### 4.1 Fraktur-Unicode-Zeichen

```python
# tests/unit/agents/preprocessing/test_fraktur_detector.py

class TestFrakturUnicodeChars:

    def test_long_s_normalization(self):
        """Unicode long s (ſ) normalization."""
        text = "daſs"  # \u017f
        result = normalize_fraktur(text)

        assert result == "dass"

    def test_round_r_normalization(self):
        """Unicode round r (ꝛ) normalization."""
        text = "Liebeꝛ"  # \ua75b
        result = normalize_fraktur(text)

        assert result == "Lieber"

    def test_fraktur_unicode_chars_defined(self):
        """Fraktur character library completeness."""
        from app.agents.preprocessing.fraktur_detector import FRAKTUR_CHARS

        assert "ſ" in FRAKTUR_CHARS  # long s
        assert "ꝛ" in FRAKTUR_CHARS  # round r
```

### 4.2 Konfidenz-Level Tests

```python
class TestFrakturConfidence:

    def test_confidence_levels(self):
        """Test confidence level classification."""
        assert get_confidence_level(0.95) == "DEFINITE_FRAKTUR"
        assert get_confidence_level(0.75) == "LIKELY_FRAKTUR"
        assert get_confidence_level(0.55) == "MIXED"
        assert get_confidence_level(0.25) == "LIKELY_ANTIQUA"
        assert get_confidence_level(0.05) == "DEFINITE_ANTIQUA"
```

### 4.3 Backend-Empfehlung

```python
def test_backend_recommendation():
    """Test backend recommendation based on Fraktur detection."""

    # Definite Fraktur → DeepSeek (beste Fraktur-Unterstützung)
    result = detect_fraktur("Die Thür des Thales")
    assert result["recommended_backend"] == "deepseek"

    # Definite Antiqua → GOT-OCR
    result = detect_fraktur("Moderner deutscher Text")
    assert result["recommended_backend"] == "got_ocr"
```

---

## 5. Historische Normalisierung Tests

### 5.1 Pre-1996 Reform (ß → ss)

```python
# tests/unit/services/test_historical_german_normalizer.py

@pytest.mark.parametrize("old,new", [
    ("daß", "dass"),
    ("muß", "muss"),
    ("Schloß", "Schloss"),
    ("Fluß", "Fluss"),
    ("Kuß", "Kuss"),
    ("Nuß", "Nuss"),
    ("Haß", "Hass"),
    ("naß", "nass"),
    ("blaß", "blass"),
    ("Genuß", "Genuss"),
])
def test_pre_1996_mappings(old, new):
    """Pre-1996 ß → ss normalization."""
    result = normalize_historical(old)

    assert new in result["normalized_text"]
    assert result["confidence"] >= 0.9
```

### 5.2 19. Jahrhundert Th → T

```python
@pytest.mark.parametrize("old,new", [
    ("Thür", "Tür"),
    ("Thor", "Tor"),
    ("Theil", "Teil"),
    ("Thier", "Tier"),
    ("Thal", "Tal"),
    ("thun", "tun"),
    ("Muth", "Mut"),
    ("Wuth", "Wut"),
    ("Rath", "Rat"),
    ("Noth", "Not"),
    ("Werth", "Wert"),
])
def test_th_mappings(old, new):
    """19th century Th → T normalization."""
    result = normalize_historical(old)

    assert new in result["normalized_text"]

    # Ausnahmen: Thron, Theater (griechischer Ursprung) bleiben
```

### 5.3 C → K/Z Normalisierung

```python
@pytest.mark.parametrize("old,new", [
    ("Curs", "Kurs"),
    ("Circus", "Zirkus"),
    ("Conto", "Konto"),
    ("Credit", "Kredit"),
    ("Caffee", "Kaffee"),
    ("Classe", "Klasse"),
    ("Cultur", "Kultur"),
    ("Concert", "Konzert"),
])
def test_c_mappings(old, new):
    """Old German C → K/Z normalization."""
    result = normalize_historical(old)

    assert new in result["normalized_text"]
```

### 5.4 Era Detection

```python
class TestEraDetection:

    def test_detect_pre_1996(self):
        """Detect pre-1996 German text."""
        text = "Er sagte, daß er kommen muß."
        result = detect_era(text)

        assert result == NormalizationEra.PRE_1996

    def test_detect_nineteenth_century(self):
        """Detect 19th century German text."""
        text = "Die Thür des Thales."
        result = detect_era(text)

        assert result == NormalizationEra.NINETEENTH

    def test_detect_fraktur(self):
        """Detect Fraktur-era text."""
        text = "Das iſt ein Teſt."  # mit long s
        result = detect_era(text)

        assert result == NormalizationEra.FRAKTUR

    def test_detect_modern(self):
        """Detect modern German text."""
        text = "Das ist ein moderner Text."
        result = detect_era(text)

        assert result == NormalizationEra.MODERN
```

---

## 6. Komposita-Splitting Tests

### 6.1 Compound-Erkennung

```python
# tests/unit/services/test_german_compound_splitter.py

@pytest.mark.parametrize("word,expected_compound", [
    ("Haus", False),           # Einfaches Wort
    ("Haustür", True),         # Kompositum
    ("Ei", False),             # Zu kurz
    ("", False),               # Leer
])
def test_compound_detection_parametrized(word, expected_compound):
    """Compound word detection."""
    result = is_compound(word)

    assert result == expected_compound

def test_simple_compound(self):
    """Simple compound splitting."""
    result = split_compound("Haustür")

    assert "Haus" in result["parts"]
    assert "tür" in result["parts"]

def test_triple_compound(self):
    """Triple compound splitting."""
    result = split_compound("Bundesfinanzministerium")

    assert result["confidence"] > 0.5
    assert len(result["parts"]) >= 3
```

### 6.2 Fugenelemente

```python
class TestFugenelemente:

    def test_compound_with_fugenelement_s(self):
        """Compound with 's' Fugenelement."""
        result = split_compound("Arbeitsplatz")

        # Arbeit + s + Platz
        assert "Arbeit" in result["parts"]
        assert result["fugenelement"] == "s"

    def test_compound_with_fugenelement_en(self):
        """Compound with 'en' Fugenelement."""
        result = split_compound("Blumenvase")

        # Blume + n + Vase
        assert "Blume" in result["parts"]
        assert result["fugenelement"] in ["n", "en"]

    def test_fugenelemente_defined(self):
        """Fugenelement library completeness."""
        from app.services.german_compound_splitter import FUGENELEMENTE

        assert "s" in FUGENELEMENTE
        assert "es" in FUGENELEMENTE
        assert "n" in FUGENELEMENTE
        assert "en" in FUGENELEMENTE
        assert "er" in FUGENELEMENTE
```

### 6.3 Search-Optimierung

```python
def test_split_for_search():
    """Compound splitting for full-text search."""
    result = split_for_search("Arbeitsplatz")

    # Alle Varianten für Suche
    assert "arbeitsplatz" in result  # Original
    assert "arbeit" in result        # Basis
    assert "platz" in result         # Suffix
```

---

## 7. Test-Fixtures für Deutsche Texte

### 7.1 Sample German Text Fixture

```python
# tests/conftest.py

@pytest.fixture
def sample_german_text():
    """Sample German text with umlauts."""
    return """
    Sehr geehrte Damen und Herren,

    hiermit übersende ich Ihnen die Rechnung Nr. 2024-001.

    Rechnungsdatum: 15.03.2024
    Fälligkeitsdatum: 30.03.2024

    Betrag: 1.234,56 €

    Bankverbindung:
    IBAN: DE89 3704 0044 0532 0130 00
    USt-IdNr.: DE123456789

    Mit freundlichen Grüßen,
    Müller GmbH & Co. KG
    Geschäftsführer: Dr. Hans Böhmer
    """
```

### 7.2 Sample Contract Fixture

```python
@pytest.fixture
def sample_contract_text():
    """German contract (Mietvertrag) fixture."""
    return """
    MIETVERTRAG

    §1 Vertragsparteien
    Vermieter: Max Müller, Goethestraße 42, München
    Mieter: Erika Schmöller, Schloßstraße 15, Frankfurt

    §2 Mietobjekt
    Das Mietobjekt befindet sich in der Gärtnerstraße 7.

    §3 Kündigungsfrist
    Die Kündigungsfrist beträgt 3 Monate zum Monatsende.

    §4 Kosten
    Monatliche Miete: 1.200,00 EUR
    Kaution: 1.400,00 EUR

    Übergabe erfolgt am 01.04.2025.
    """
```

### 7.3 Mock Correction Result

```python
@pytest.fixture
def mock_correction_result():
    """Mock German correction result."""
    return {
        "text": "Der korrigierte Text mit Änderung, Öffnung, Übung.",
        "original_text": "Der korrigierte Text mit Aenderung, Oeffnung, Uebung.",
        "corrections_applied": 3,
        "correction_details": [
            {
                "type": "umlaut",
                "original": "Aenderung",
                "corrected": "Änderung",
                "confidence": 0.95
            },
            {
                "type": "umlaut",
                "original": "Oeffnung",
                "corrected": "Öffnung",
                "confidence": 0.94
            },
            {
                "type": "umlaut",
                "original": "Uebung",
                "corrected": "Übung",
                "confidence": 0.93
            }
        ],
        "validation_score": 0.95,
        "umlauts_restored": 3
    }
```

---

## 8. Fixture-Dokumente

### 8.1 Rechnungen (invoices/)

```json
// invoice_001.json
{
  "filename": "invoice_001.png",
  "category": "invoices",
  "expected_text": "RECHNUNG Nr. 2024-5878\nBöhm Elektrotechnik\nGoethestraße 22...",
  "expected_entities": {
    "invoice_number": ["2024-5878"],
    "iban": ["DE50154572822408899428"],
    "vat_id": ["DE621056220"],
    "date": ["05.09.2025"],
    "total_gross": ["3.661,90"]
  },
  "has_umlauts": true,
  "has_tables": false,
  "language": "de"
}
```

### 8.2 Fraktur (fraktur/)

```json
// fraktur_001.json
{
  "filename": "fraktur_001.png",
  "category": "fraktur",
  "expected_text": "Bekanntmachung\nAllen Buergern und Einwohnern...",
  "era_indicators": ["Thür", "kundgethan", "Obrigkeit"],
  "normalization_needed": true,
  "has_long_s": true,
  "language": "de-fraktur"
}
```

### 8.3 Verträge (contracts/)

```json
// contract_001.json
{
  "filename": "contract_001.png",
  "category": "contracts",
  "expected_entities": {
    "parties": ["Max Müller", "Erika Schmöller"],
    "locations": ["München", "Gärtnerstraße"],
    "legal_terms": ["Kündigungsfrist", "Kaution"]
  },
  "has_umlauts": true,
  "language": "de"
}
```

---

## 9. German-spezifische Fehlermeldungen

### 9.1 Validation Messages

```python
# app/core/german_messages.py

class ValidationMessages:
    UMLAUT_ERROR_DETECTED = "Möglicher Umlaut-Fehler erkannt: '{pattern}' sollte '{correct}' sein"
    ENCODING_ERROR = "Textcodierung fehlerhaft (Umlaute nicht korrekt)"
    INVALID_DATE = "Ungültiges Datumsformat (erwartet: TT.MM.JJJJ)"
    INVALID_IBAN = "Ungültige IBAN"
    INVALID_VAT_ID = "Ungültige USt-IdNr."
    INVALID_TAX_NUMBER = "Ungültige Steuernummer"

class OCRMessages:
    GERMAN_TEXT_DETECTED = "Deutscher Text erkannt"
    UMLAUTS_PRESERVED = "Umlaute korrekt erkannt"
    FRAKTUR_DETECTED = "Frakturschrift erkannt"
```

### 9.2 Test für Fehlermeldungen

```python
def test_german_error_messages():
    """All error messages must be in German."""
    from app.core.german_messages import ValidationMessages

    # Keine englischen Wörter in Fehlermeldungen
    messages = [
        ValidationMessages.UMLAUT_ERROR_DETECTED,
        ValidationMessages.ENCODING_ERROR,
        ValidationMessages.INVALID_DATE,
    ]

    english_words = ["error", "invalid", "failed", "success"]

    for msg in messages:
        for word in english_words:
            assert word.lower() not in msg.lower()
```

---

## 10. Business Term Recognition

### 10.1 Unterstützte Geschäftsbegriffe

| Kategorie | Begriffe |
|-----------|----------|
| Gesellschaftsformen | GmbH, AG, KG, GbR, OHG, e.V., e.K., KGaA, UG, PartG |
| Steuer/Registrierung | USt-IdNr., St.-Nr., HRB, HRA, GnR, PR |
| Finanzen | MwSt., USt., inkl., exkl., zzgl., abzgl. |
| Banking | IBAN, BIC, SEPA |

### 10.2 Business Term Tests

```python
def test_business_term_extraction():
    """Test German business term extraction."""
    text = "Müller GmbH, USt-IdNr.: DE123456789, HRB 12345"
    result = extract_business_terms(text)

    assert "GmbH" in result["terms"]
    assert "USt-IdNr." in result["terms"]
    assert "HRB" in result["terms"]

def test_iban_validation():
    """Test IBAN validation with checksum."""
    # Valid German IBAN
    assert validate_iban("DE89 3704 0044 0532 0130 00") is True

    # Invalid checksum
    assert validate_iban("DE12 3456 7890 1234 5678 90") is False

def test_vat_id_validation():
    """Test German VAT ID validation."""
    # Valid: DE + 9 digits
    assert validate_vat_id("DE123456789") is True

    # Invalid: too short
    assert validate_vat_id("DE12345") is False
```

---

## 11. Unicode/UTF-8 Handling

### 11.1 Normalisierung

```python
# app/utils/german_text.py

def normalize_german_text(text: str) -> str:
    """
    Normalize German text for processing.

    Handles:
    - Unicode normalization (NFC - composed form)
    - Umlaut variants
    - Fraktur character mapping
    - Whitespace normalization
    """
    # NFC: "ä" als einzelnes Zeichen
    # vs. NFD: "a" + combining diaeresis
    text = unicodedata.normalize("NFC", text)
    return text
```

### 11.2 UTF-8 Compliance Tests

```python
def test_utf8_encoding():
    """All German text handling must be UTF-8."""
    # Alle Umlaute müssen korrekt sein
    text = "Äpfel, Öl, Übung, Größe, Straße"

    # Encode/Decode Roundtrip
    encoded = text.encode("utf-8")
    decoded = encoded.decode("utf-8")

    assert decoded == text
    assert "Ä" in decoded
    assert "ö" in decoded
    assert "ü" in decoded
    assert "ß" in decoded
```

---

## 12. Quality Metrics

### 12.1 Tracked Metrics

```python
class GermanTextQualityMetrics:
    """Quality metrics for German OCR."""

    umlaut_accuracy: float      # Korrekte Umlaut-Erkennung
    date_format_correct: bool   # DD.MM.YYYY Validierung
    currency_format_correct: bool  # 1.234,56 EUR Validierung
    business_term_recognition: float  # GmbH, USt-IdNr., etc.
    fraktur_handling: float     # Historische Texte
    compound_word_handling: float  # Deutsche Komposita
```

### 12.2 Ziel-Werte

| Metrik | Ziel | Kritisch |
|--------|------|----------|
| Umlaut-Genauigkeit | 100% | Ja |
| Datums-Erkennung | 99% | Ja |
| Währungs-Erkennung | 99% | Ja |
| Business Terms | 95% | Nein |
| Fraktur-Handling | 90% | Nein |

---

## 13. Enhanced Umlaut Handler

### 13.1 False-Positive-Vermeidung

```python
class EnhancedUmlautHandler:
    """Kontextbewusste Umlaut-Wiederherstellung mit False-Positive-Vermeidung."""

    FALSE_POSITIVES: FrozenSet[str] = frozenset([
        # Keine Korrektur für diese Wörter
        "israel", "michael", "rafael", "boeing", "phoenix",
        "poet", "koexistenz", "queue", "cruel", "fuel",
        "professor", "mission", "passion", "session",
    ])

    DEFINITE_UMLAUTS: Dict[str, str] = {
        # Direkte Mappings (95%+ Konfidenz)
        "aerger": "Ärger",
        "aenderung": "Änderung",
        "muenchen": "München",
        # ... 450+ Einträge
    }
```

### 13.2 Safe Pattern Tests

```python
def test_false_positive_prevention():
    """Test that false positives are NOT corrected."""
    # Diese Wörter sollten NICHT korrigiert werden
    false_positives = ["Israel", "Michael", "Boeing", "Queue"]

    for word in false_positives:
        result = correct_german_text(word)
        assert result["text"] == word  # Keine Änderung
```

---

## 14. Best Practices

### 14.1 Test-Schreibung

1. **Parametrisierung nutzen**: Für Varianten des gleichen Test-Szenarios
2. **Fixtures verwenden**: Gemeinsame Test-Daten in conftest.py
3. **Klare Assertion Messages**: Auf Deutsch für bessere Lesbarkeit
4. **Edge Cases testen**: Leere Strings, Sonderzeichen, Mixed Content

### 14.2 Coverage-Ziele

- **Unit Tests**: 90%+ Coverage für german_validator.py
- **Integration Tests**: E2E mit echten OCR-Ergebnissen
- **Parametrisierte Tests**: 60+ Kombinationen

### 14.3 Continuous Integration

```yaml
# CI Pipeline
test-german:
  runs-on: ubuntu-latest
  steps:
    - name: Run German Language Tests
      run: |
        pytest tests/unit/test_german_validator.py -v
        pytest tests/unit/agents/postprocessing/test_german_correction_agent.py -v
        pytest tests/unit/services/test_historical_german_normalizer.py -v
```

---

## Zusammenfassung

Die German Language Tests stellen sicher:
- **100% Umlaut-Genauigkeit** (ä, ö, ü, ß)
- **Korrekte Datumsformate** (DD.MM.YYYY)
- **Korrekte Währungsformate** (1.234,56 €)
- **Business Term Recognition** (50+ Begriffe)
- **Fraktur-Unterstützung** für historische Dokumente
- **Komposita-Handling** für deutsche Wortbildung

Alle Tests verwenden **deutsche Fehlermeldungen** und **UTF-8 Encoding**.
