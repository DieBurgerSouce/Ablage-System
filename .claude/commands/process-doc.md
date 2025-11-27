# Process Document Command

Verarbeitet ein einzelnes Dokument mit OCR.

**Anweisungen:**

1. **Dokument validieren:**
   - Prüfe Dateityp (PDF, PNG, JPG, TIFF)
   - Prüfe Dateigröße (<50MB)
   - Erstelle Vorschau falls möglich

2. **Backend auswählen:**
   - `auto` - Automatische Auswahl basierend auf Dokumenttyp
   - `deepseek` - Für komplexe Layouts, Fraktur, beste Umlaut-Genauigkeit
   - `got_ocr` - Für Tabellen, Formeln, schnelle Verarbeitung
   - `surya` - CPU-Fallback, immer verfügbar

3. **OCR ausführen:**
```python
from app.services.ocr_service import OCRService

service = OCRService()
result = await service.process_document(
    file_path="$ARGUMENTS",
    backend="auto"
)
```

4. **Ergebnis validieren:**
   - Deutsche Text-Validierung durchführen
   - Entitäten extrahieren (IBAN, Datum, Beträge)
   - Konfidenz-Score prüfen

5. **Ausgabe:**
```
=== OCR-Ergebnis ===

Datei: rechnung_2024.pdf
Backend: DeepSeek
Verarbeitungszeit: 1.8s
GPU-Speicher: 11.2GB

--- Extrahierter Text ---
[Text hier]

--- Extrahierte Entitäten ---
IBAN: DE89370400440532013000
Datum: 15.03.2024
Betrag: 1.234,56 EUR
USt-IdNr: DE123456789

Validierung: ✓ BESTANDEN (Umlaut-Genauigkeit: 99.8%)
```

**Argumente:**
- `$ARGUMENTS` - Pfad zum Dokument
