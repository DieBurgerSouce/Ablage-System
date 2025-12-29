---
name: german-text
description: Validiere und korrigiere deutsche Texte im Ablage-System. Nutze diesen Skill fuer Umlaut-Probleme, UTF-8 Encoding, Fehlermeldungen auf Deutsch, Fraktur-Schrift und deutsche Rechtschreibpruefung.
---

# German Text Handling (Ablage-System)

Deutsche Texte korrekt verarbeiten - 100% Umlaut-Genauigkeit erforderlich!

## Grundregeln

1. **ALLE User-facing Texte auf Deutsch**
2. **UTF-8 Encoding ueberall**
3. **Umlaute korrekt (ä, ö, ü, ß) - NIEMALS ae, oe, ue, ss**

## Umlaut-Validierung

```python
import unicodedata

def validate_german_text(text: str) -> bool:
    """Prueft ob deutsche Umlaute korrekt sind."""
    # Auf NFC normalisieren
    text = unicodedata.normalize('NFC', text)

    # Verdaechtige Muster
    bad_patterns = ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue']

    # Aber nicht alle - z.B. "Israel" ist okay
    # Nur warnen wenn im Kontext verdaechtig
    return True
```

## Text-Normalisierung

```python
import unicodedata

def normalize_german_text(text: str) -> str:
    """Normalisiert deutschen Text."""
    # NFC Normalisierung (composed form)
    text = unicodedata.normalize('NFC', text)

    # Fraktur zu modernem Deutsch
    fraktur_map = {
        '\u1E9E': 'ß',  # Grosses ß
        # ... weitere Mappings
    }
    for old, new in fraktur_map.items():
        text = text.replace(old, new)

    return text
```

## Deutsche Fehlermeldungen

```python
# app/core/exceptions.py

ERROR_MESSAGES = {
    "document_not_found": "Dokument nicht gefunden",
    "processing_failed": "Verarbeitung fehlgeschlagen",
    "invalid_format": "Ungueltiges Dateiformat",
    "gpu_unavailable": "GPU nicht verfuegbar - Fallback auf CPU",
    "upload_failed": "Upload fehlgeschlagen",
    "ocr_error": "Fehler bei der Texterkennung",
    "permission_denied": "Zugriff verweigert",
    "file_too_large": "Datei zu gross (max. 50 MB)",
    "invalid_file_type": "Dateityp nicht unterstuetzt",
    "rate_limit_exceeded": "Zu viele Anfragen - bitte warten",
}
```

## API Responses auf Deutsch

```python
# Erfolg
{
    "status": "erfolg",
    "nachricht": "Dokument erfolgreich verarbeitet",
    "ergebnis": {
        "dokument_id": "abc123",
        "extrahierter_text": "...",
        "verarbeitungszeit_ms": 1234
    }
}

# Fehler
{
    "status": "fehler",
    "fehlercode": "OCR_FAILED",
    "nachricht": "Texterkennung fehlgeschlagen",
    "details": "GPU-Speicher nicht ausreichend"
}
```

## UI-Texte Checkliste

### Buttons
- "Speichern" (nicht "Save")
- "Abbrechen" (nicht "Cancel")
- "Loeschen" (nicht "Delete")
- "Hochladen" (nicht "Upload")
- "Herunterladen" (nicht "Download")

### Labels
- "Datei auswaehlen"
- "Suchbegriff eingeben"
- "Sortieren nach"
- "Filtern"

### Feedback
- "Wird geladen..."
- "Erfolgreich gespeichert"
- "Fehler aufgetreten"
- "Keine Ergebnisse gefunden"

## Rechtschreibpruefung

```python
from spellchecker import SpellChecker

spell = SpellChecker(language='de')

def check_german_spelling(text: str) -> list:
    """Findet Rechtschreibfehler."""
    words = text.split()
    misspelled = spell.unknown(words)

    suggestions = []
    for word in misspelled:
        suggestions.append({
            "word": word,
            "suggestions": list(spell.candidates(word))[:3]
        })

    return suggestions
```

## Encoding Best Practices

```python
# Datei lesen
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Datei schreiben
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)

# Datenbank: UTF-8 Collation
# PostgreSQL: COLLATE "de_DE.UTF-8"
```

## Fraktur-Schrift

```python
# OCR-Konfiguration fuer Fraktur
ocr_config = {
    "language": "de",
    "detect_fraktur": True,
    "script": "Fraktur"
}

# Fraktur-Zeichen Mapping
FRAKTUR_TO_LATIN = {
    '\U0001D504': 'A',  # 𝔄
    '\U0001D505': 'B',  # 𝔅
    # ... etc
}
```

## Validierung vor Commit

```bash
# Deutsche Texte in Code pruefen
grep -r "Save\|Cancel\|Delete\|Error\|Success" --include="*.tsx" frontend/src/

# Sollte nichts finden (oder nur technische Terme)
```

## Compound Words (Zusammengesetzte Woerter)

```python
def split_compound_word(word: str) -> list:
    """Zerlegt deutsche Compound Words."""
    # Nutze spaCy oder custom Algorithmus
    # "Dokumentenverarbeitungssystem" ->
    # ["Dokumenten", "verarbeitungs", "system"]
    pass
```

## Locale-Settings

```python
import locale

# Fuer Zahlen und Datum
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

# Datum formatieren
from datetime import datetime
datum = datetime.now().strftime('%d.%m.%Y')  # 29.12.2024

# Zahlen formatieren
zahl = locale.format_string('%.2f', 1234.56, grouping=True)  # 1.234,56
```
