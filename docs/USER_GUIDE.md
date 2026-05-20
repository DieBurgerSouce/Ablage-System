# Ablage-System Benutzerhandbuch

> **Version:** 1.0
> **Stand:** Januar 2025
> **Zielgruppe:** Endanwender und Business-Nutzer

---

## Inhaltsverzeichnis

1. [Einführung](#einführung)
2. [Erste Schritte](#erste-schritte)
3. [Dokumente verarbeiten](#dokumente-verarbeiten)
4. [Suche und Navigation](#suche-und-navigation)
5. [Dokumenttypen](#dokumenttypen)
6. [OCR-Ergebnisse](#ocr-ergebnisse)
7. [Tastenkürzel](#tastenkürzel)
8. [Häufige Fragen](#häufige-fragen)

---

## Einführung

### Was ist Ablage-System?

Ablage-System ist eine intelligente Dokumentenverarbeitung, die Ihre Papierdokumente digitalisiert und durchsuchbar macht. Das System erkennt automatisch:

- **Text** aus gescannten Dokumenten (OCR)
- **Dokumenttypen** (Rechnung, Vertrag, Brief, etc.)
- **Strukturierte Daten** (Beträge, Daten, Adressen)
- **Deutsche Texte** mit Umlauten und ß

### Hauptfunktionen

| Funktion | Beschreibung |
|----------|--------------|
| **Dokumenten-Upload** | Laden Sie PDFs, Bilder und gescannte Dokumente hoch |
| **Automatische OCR** | Texterkennung läuft automatisch im Hintergrund |
| **Volltextsuche** | Durchsuchen Sie alle Dokumente nach Stichworten |
| **Kategorisierung** | Automatische Zuordnung zu Dokumenttypen |
| **Export** | Exportieren Sie Ergebnisse als CSV, JSON oder PDF |

---

## Erste Schritte

### 1. Anmeldung

1. Öffnen Sie die Ablage-System URL in Ihrem Browser
2. Geben Sie Ihre E-Mail-Adresse ein
3. Geben Sie Ihr Passwort ein
4. Klicken Sie auf **"Anmelden"**

> **Tipp:** Aktivieren Sie "Angemeldet bleiben" für schnelleren Zugriff

### 2. Dashboard-Übersicht

Nach der Anmeldung sehen Sie das Dashboard:

```
┌─────────────────────────────────────────────────────────────┐
│  Ablage-System                              [Suche...]  👤  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Statistiken          📄 Letzte Dokumente               │
│  ┌─────────────────┐    ┌───────────────────────────────┐  │
│  │ Dokumente: 1,234│    │ • Rechnung_2025-01.pdf       │  │
│  │ Heute: 12       │    │ • Vertrag_Muster.pdf         │  │
│  │ Ausstehend: 3   │    │ • Brief_Finanzamt.pdf        │  │
│  └─────────────────┘    └───────────────────────────────┘  │
│                                                             │
│  [+ Neues Dokument]                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. Anzeigemodus wählen

Ablage-System bietet vier Anzeigemodi für verschiedene Situationen:

| Modus | Beschreibung | Wann verwenden |
|-------|--------------|----------------|
| **Dark Mode** | Dunkler Hintergrund | Standard, abends |
| **Light Mode** | Heller Hintergrund | Tagsüber, helle Umgebung |
| **Whitescreen** | Hoher Kontrast (weiß) | Sehbeeinträchtigung, Präsentation |
| **Blackscreen** | Hoher Kontrast (schwarz) | OLED-Displays, sehr dunkel |

**Modus wechseln:** Klicken Sie auf ⚙️ Einstellungen → Anzeige → Modus wählen

---

## Dokumente verarbeiten

### Dokumente hochladen

#### Methode 1: Drag & Drop

1. Ziehen Sie eine Datei vom Desktop
2. Lassen Sie sie im Upload-Bereich fallen
3. Die Verarbeitung startet automatisch

#### Methode 2: Dateiauswahl

1. Klicken Sie auf **[+ Neues Dokument]**
2. Wählen Sie **"Datei auswählen"**
3. Navigieren Sie zur Datei
4. Klicken Sie **"Öffnen"**

#### Methode 3: Mehrere Dateien

1. Klicken Sie auf **"Batch-Upload"**
2. Wählen Sie mehrere Dateien (Strg + Klick)
3. Alle Dateien werden parallel verarbeitet

### Unterstützte Formate

| Format | Endung | Max. Größe | Hinweise |
|--------|--------|------------|----------|
| PDF | .pdf | 50 MB | Auch mehrseitig |
| JPEG | .jpg, .jpeg | 20 MB | Fotos, Scans |
| PNG | .png | 20 MB | Screenshots |
| TIFF | .tif, .tiff | 100 MB | Professionelle Scans |
| WebP | .webp | 20 MB | Moderne Browser |

### Verarbeitungsstatus

Nach dem Upload sehen Sie den Status:

| Status | Symbol | Bedeutung |
|--------|--------|-----------|
| Hochgeladen | ⬆️ | Datei empfangen |
| In Warteschlange | ⏳ | Warten auf Verarbeitung |
| Verarbeitung | 🔄 | OCR läuft |
| Abgeschlossen | ✅ | Text erkannt |
| Fehler | ❌ | Problem aufgetreten |

> **Typische Verarbeitungszeit:** 2-10 Sekunden pro Seite

### OCR-Backend auswählen

Für spezielle Dokumente können Sie das OCR-Backend wählen:

| Backend | Stärken | Wann verwenden |
|---------|---------|----------------|
| **Auto** (Standard) | Automatische Auswahl | Normale Dokumente |
| **DeepSeek** | Komplexe Layouts | Tabellen, Formulare |
| **GOT-OCR** | Schnell | Einfache Texte, Masse |
| **Surya** | Layoutanalyse | Zeitungen, Magazine |

**Backend wählen:** Erweiterte Optionen → OCR-Backend

---

## Suche und Navigation

### Volltextsuche

1. Klicken Sie in die Suchleiste (oder drücken Sie `/`)
2. Geben Sie Ihren Suchbegriff ein
3. Ergebnisse erscheinen sofort

#### Suchoperatoren

| Operator | Beispiel | Findet |
|----------|----------|--------|
| Einfach | `Rechnung` | Alle mit "Rechnung" |
| Phrase | `"Finanzamt München"` | Exakte Phrase |
| UND | `Rechnung AND 2025` | Beides enthalten |
| ODER | `Rechnung OR Invoice` | Eines enthalten |
| NICHT | `Rechnung NOT Storno` | Ohne "Storno" |
| Wildcard | `Rech*` | Rechnung, Rechner, etc. |

#### Filteroptionen

- **Datum:** Letzte 7 Tage, Monat, Jahr, benutzerdefiniert
- **Typ:** Rechnung, Vertrag, Brief, etc.
- **Status:** Abgeschlossen, Ausstehend, Fehler
- **Ordner:** Nach Ordnerstruktur filtern

### Dokumentenansicht

Doppelklicken Sie auf ein Dokument für die Detailansicht:

```
┌─────────────────────────────────────────────────────────────┐
│ Rechnung_2025-01.pdf                           [X] Schließen│
├────────────────────────────┬────────────────────────────────┤
│                            │                                │
│   [Original-PDF Vorschau]  │  📝 Extrahierter Text          │
│                            │  ─────────────────────────     │
│                            │  Rechnung Nr. 12345            │
│                            │  Datum: 15.01.2025             │
│                            │  Betrag: 1.234,56 €            │
│                            │                                │
│                            │  📊 Erkannte Daten             │
│                            │  ─────────────────────────     │
│                            │  • Rechnungsnummer: 12345      │
│                            │  • Datum: 15.01.2025           │
│                            │  • Betrag: 1.234,56 €          │
│                            │  • MwSt: 19%                   │
│                            │                                │
└────────────────────────────┴────────────────────────────────┘
```

### Ordner und Tags

#### Ordner erstellen

1. Klicken Sie auf **"Neuer Ordner"** in der Seitenleiste
2. Geben Sie einen Namen ein
3. Ziehen Sie Dokumente in den Ordner

#### Tags vergeben

1. Wählen Sie ein oder mehrere Dokumente
2. Klicken Sie auf **"Tags"**
3. Wählen Sie bestehende Tags oder erstellen Sie neue
4. Tags helfen bei der späteren Filterung

---

## Dokumenttypen

### Automatische Erkennung

Ablage-System erkennt automatisch diese Dokumenttypen:

| Typ | Erkannte Felder | Beispiele |
|-----|-----------------|-----------|
| **Rechnung** | Nummer, Datum, Betrag, MwSt | Lieferantenrechnungen, Stromrechnung |
| **Vertrag** | Parteien, Datum, Laufzeit | Mietvertrag, Arbeitsvertrag |
| **Brief** | Absender, Empfänger, Datum | Behördenschreiben, Korrespondenz |
| **Beleg** | Datum, Betrag, Händler | Kassenbon, Quittung |
| **Ausweis** | Name, Nummer, Gültigkeit | Personalausweis, Führerschein |
| **Formular** | Felder je nach Typ | Anträge, Fragebögen |

### Manuelle Korrektur

Falls der Dokumenttyp falsch erkannt wurde:

1. Öffnen Sie das Dokument
2. Klicken Sie auf **"Typ ändern"**
3. Wählen Sie den korrekten Typ
4. Das System lernt aus Ihren Korrekturen

---

## OCR-Ergebnisse

### Text bearbeiten

Falls OCR-Fehler auftreten:

1. Öffnen Sie das Dokument
2. Klicken Sie auf **"Text bearbeiten"**
3. Korrigieren Sie Fehler direkt
4. Klicken Sie **"Speichern"**

> **Tipp:** Korrekturen verbessern die automatische Erkennung für zukünftige ähnliche Dokumente

### Qualitätsbewertung

Jedes Dokument zeigt eine Qualitätsbewertung:

| Bewertung | Bedeutung |
|-----------|-----------|
| ⭐⭐⭐⭐⭐ (95-100%) | Exzellent - Keine Überprüfung nötig |
| ⭐⭐⭐⭐ (85-94%) | Sehr gut - Stichproben-Check |
| ⭐⭐⭐ (70-84%) | Gut - Kritische Felder prüfen |
| ⭐⭐ (50-69%) | Mäßig - Manuelle Überprüfung empfohlen |
| ⭐ (<50%) | Schlecht - Vollständige Überprüfung nötig |

### Export

#### Einzelnes Dokument exportieren

1. Öffnen Sie das Dokument
2. Klicken Sie auf **"Exportieren"**
3. Wählen Sie das Format:
   - **PDF** - Mit Text-Layer (durchsuchbar)
   - **TXT** - Nur extrahierter Text
   - **JSON** - Strukturierte Daten

#### Mehrere Dokumente exportieren

1. Wählen Sie mehrere Dokumente (Checkbox)
2. Klicken Sie auf **"Batch-Export"**
3. Wählen Sie Format und Optionen:
   - **ZIP** - Alle Dateien einzeln
   - **CSV** - Metadaten als Tabelle
   - **PDF** - Zusammengefasst

---

## Tastenkürzel

### Navigation

| Kürzel | Aktion |
|--------|--------|
| `/` | Suche fokussieren |
| `Esc` | Dialog schließen |
| `↑` / `↓` | Durch Liste navigieren |
| `Enter` | Dokument öffnen |
| `Backspace` | Zurück zur Liste |

### Dokumentverwaltung

| Kürzel | Aktion |
|--------|--------|
| `Strg + U` | Upload-Dialog öffnen |
| `Strg + F` | Volltextsuche |
| `Strg + E` | Exportieren |
| `Strg + D` | Herunterladen |
| `Del` | In Papierkorb verschieben |

### Auswahl

| Kürzel | Aktion |
|--------|--------|
| `Strg + A` | Alle auswählen |
| `Strg + Klick` | Zur Auswahl hinzufügen |
| `Shift + Klick` | Bereich auswählen |

### Anzeigemodus

| Kürzel | Aktion |
|--------|--------|
| `Alt + 1` | Dark Mode |
| `Alt + 2` | Light Mode |
| `Alt + 3` | Whitescreen |
| `Alt + 4` | Blackscreen |

---

## Häufige Fragen

### Wie lange dauert die OCR-Verarbeitung?

- **Einzelne Seite:** 2-5 Sekunden
- **Mehrseitiges PDF (10 Seiten):** 20-50 Sekunden
- **Große Batches:** Parallel, je nach Serverlast

### Warum wurde mein Dokument nicht erkannt?

Mögliche Ursachen:
1. **Schlechte Scan-Qualität** - Mindestens 200 DPI empfohlen
2. **Schräger Scan** - Dokument gerade scannen
3. **Handschrift** - Derzeit eingeschränkte Unterstützung
4. **Beschädigte Datei** - Datei neu scannen

### Wie kann ich die Genauigkeit verbessern?

1. **Bessere Scans** - 300 DPI, gerade, guter Kontrast
2. **DeepSeek-Backend** - Für komplexe Dokumente
3. **Korrekturen einreichen** - System lernt mit

### Werden meine Dokumente in der Cloud gespeichert?

**Nein!** Ablage-System ist komplett On-Premises. Alle Daten bleiben auf Ihren lokalen Servern.

### Wie lösche ich ein Dokument endgültig?

1. Dokument in den Papierkorb verschieben
2. Papierkorb öffnen
3. "Endgültig löschen" wählen

> **Hinweis:** Nach DSGVO-Vorgaben werden Dokumente nach der Aufbewahrungsfrist automatisch gelöscht.

### Kann ich Dokumente mit anderen teilen?

Ja! Über die Freigabe-Funktion:
1. Dokument auswählen
2. "Freigeben" klicken
3. E-Mail des Empfängers eingeben
4. Berechtigungen wählen (Anzeigen/Bearbeiten)

---

## Support

Bei Fragen oder Problemen:

- **Interne Hilfe:** Klicken Sie auf ❓ in der Anwendung
- **Schulungsmaterialien:** Verfügbar im Intranet
- **IT-Support:** support@ihre-firma.de
- **Hotline:** +49 123 456789

---

*Letzte Aktualisierung: Januar 2025*
