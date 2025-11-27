# Validate German Text Command

Validiert deutsche Texte auf korrekte Formatierung und Umlaute.

**Anweisungen:**

1. Text oder Datei analysieren auf:
   - Umlaut-Korrektheit (ä, ö, ü, ß)
   - Datumsformat (DD.MM.YYYY)
   - Währungsformat (1.234,56 EUR)
   - IBAN-Format (DE + 20 Ziffern)
   - USt-IdNr Format

2. Validator ausführen:
```python
from app.german_validator import GermanValidator

validator = GermanValidator()
result = validator.validate_all(text)
print(result.summary())
```

3. Bei Fehlern:
   - Zeige problematische Stellen
   - Schlage Korrekturen vor
   - Prüfe OCR-Backend-Empfehlung (DeepSeek für beste Umlaut-Genauigkeit)

**Beispiel-Ausgabe:**
```
=== Deutsche Text-Validierung ===

Umlaute: ✓ 15 gefunden, alle korrekt
Datumsformate: ✓ 3 Daten im Format DD.MM.YYYY
Währungen: ✓ 2 Beträge korrekt formatiert
IBAN: ✓ DE89370400440532013000
USt-IdNr: ✓ DE123456789

Gesamtergebnis: ✓ VALIDE
```

**Argumente:**
- `$ARGUMENTS` - Text oder Dateipfad zum Validieren
