---
name: webapp-tester-mcp
description: |
  KI-gesteuertes, menschenaehnliches WebApp-Testing mit Playwright MCP Server.
  Nutze diesen Skill wenn du eine Webapp VOLLSTAENDIG und SYSTEMATISCH testen
  moechtest - wie ein erfahrener QA-Engineer. Der MCP Server haelt den Browser
  offen zwischen Aktionen fuer schnelle, zusammenhaengende Test-Sessions.
  
  WICHTIG: Erfordert aktiven Playwright MCP Server (siehe .mcp.json)
globs:
  - "frontend/**/*"
  - "tests/e2e/**/*"
  - "playwright.config.ts"
alwaysApply: false
---

# WebApp Tester MCP - Golden Pattern

## Ueberblick

Dieser Skill ermoeglicht **KI-gesteuertes, menschenaehnliches Testing** von Webapps.
Anders als klassische Test-Skripte arbeitet dieser Ansatz explorativ und adaptiv -
genau wie ein erfahrener QA-Engineer, der eine Anwendung zum ersten Mal sieht.

## Verfuegbare MCP Tools

Der Playwright MCP Server stellt folgende Tools bereit:

### Navigation & Grundlagen
| Tool | Beschreibung |
|------|-------------|
| `browser_navigate` | Zu URL navigieren |
| `browser_go_back` | Zurueck navigieren |
| `browser_go_forward` | Vorwaerts navigieren |
| `browser_wait` | Warten (ms) |
| `browser_close` | Browser schliessen |

### Interaktion
| Tool | Beschreibung |
|------|-------------|
| `browser_click` | Element klicken (via ref aus Snapshot) |
| `browser_type` | Text eingeben |
| `browser_select_option` | Dropdown-Option waehlen |
| `browser_hover` | Ueber Element hovern |
| `browser_drag` | Drag & Drop |
| `browser_press_key` | Taste druecken |

### Inspektion & Analyse
| Tool | Beschreibung |
|------|-------------|
| `browser_snapshot` | Accessibility Tree abrufen (WICHTIGSTE METHODE) |
| `browser_screenshot` | Screenshot fuer visuelle Analyse |
| `browser_console_messages` | Browser-Konsole auslesen |
| `browser_network_requests` | Netzwerk-Requests loggen |

### Fortgeschritten
| Tool | Beschreibung |
|------|-------------|
| `browser_evaluate` | JavaScript im Browser ausfuehren |
| `browser_file_upload` | Datei hochladen |
| `browser_handle_dialog` | Alert/Confirm/Prompt behandeln |

## Test-Strategie: 4-Phasen-Modell

### Phase 1: Reconnaissance (Erkundung)

**Ziel:** Verstehen was die App kann, bevor getestet wird.

```
ABLAUF:
1. browser_navigate → Startseite laden
2. browser_snapshot → Accessibility Tree analysieren
   → Alle interaktiven Elemente identifizieren
   → Navigation-Struktur erfassen
   → Formulare und Eingabefelder finden
3. browser_screenshot → Visuelle Baseline erstellen
4. Seitenstruktur dokumentieren
```

**Accessibility Tree Interpretation:**
```
Der Snapshot liefert strukturierte Daten wie:
- button "Dokument hochladen" [ref=e14]
- textbox "Suche..." [ref=e21]
- link "Dashboard" [ref=e7]

Die [ref=eXX] Werte sind die Selektoren fuer Aktionen!
```

### Phase 2: Funktionale Tests

**Ziel:** Alle Features systematisch durchpruefen.

#### Navigation testen
```
FUER JEDEN Link/Button in der Navigation:
1. browser_click(ref) → Element anklicken
2. browser_snapshot → Neuen State analysieren
3. Erwartetes Verhalten pruefen:
   - URL korrekt?
   - Seitentitel korrekt?
   - Erwartete Inhalte vorhanden?
4. browser_go_back → Zurueck navigieren
5. Wiederholung fuer naechstes Element
```

#### Formulare testen
```
FUER JEDES Formular:
1. browser_snapshot → Felder identifizieren
2. HAPPY PATH:
   - Valide Daten eingeben
   - Submit klicken
   - Erfolg pruefen
3. VALIDATION TESTS:
   - Leere Felder → Fehlermeldung?
   - Ungueltige Formate → Fehlermeldung?
   - Zu lange Eingaben → Handling?
4. EDGE CASES:
   - Sonderzeichen (ä, ö, ü, ß, €)
   - SQL Injection Patterns
   - XSS Patterns
```

#### API-Integration testen
```
1. browser_network_requests aktivieren
2. Aktion ausfuehren
3. Requests analysieren:
   - Korrekte Endpoints?
   - Korrekte HTTP Methods?
   - Response Status Codes?
```

### Phase 3: Edge Cases & Error Handling

**Ziel:** Robustheit der Anwendung pruefen.

```
CHECKLISTE:
□ Session Timeout Handling
□ Offline/Slow Network Verhalten
□ Concurrent User Actions
□ Browser Back/Forward Navigation
□ Page Refresh waehrend Aktionen
□ Sehr grosse Datensaetze
□ Leere Datensaetze
□ Berechtigungsfehler
□ API Fehler (4xx, 5xx)
```

### Phase 4: Dokumentation & Reporting

**Ziel:** Strukturierter Testbericht.

```markdown
# Testbericht: [App Name]
Datum: YYYY-MM-DD
Tester: Claude (MCP WebApp Tester)

## Zusammenfassung
- Getestete Seiten: X
- Gefundene Fehler: Y (Z kritisch)
- Test-Coverage: ~X%

## Getestete Bereiche
### 1. Navigation
- [✓] Hauptnavigation funktional
- [✓] Alle Links erreichbar
- [✗] Back-Button Bug auf /documents

### 2. Formulare
- [✓] Login funktional
- [✓] Dokument-Upload funktional
- [✗] Validation fehlt bei E-Mail Feld

### 3. Edge Cases
- [✓] Deutsche Umlaute korrekt
- [✗] Session Timeout zeigt keine Warnung

## Kritische Fehler
1. **BUG-001**: [Beschreibung]
   - Schritte zur Reproduktion
   - Screenshot: /tmp/bug-001.png
   - Erwartetes vs. tatsaechliches Verhalten

## Empfehlungen
1. ...
2. ...
```

## Ablage-System Spezifische Tests

### OCR-Upload Flow
```
1. browser_navigate("http://localhost:80/upload")
2. browser_file_upload(ref, "test_documents/rechnung_muster.pdf")
3. browser_snapshot → Fortschrittsanzeige pruefen
4. browser_wait(5000) → OCR-Verarbeitung abwarten
5. browser_snapshot → Ergebnisse pruefen:
   - Extrahierter Text vorhanden?
   - Strukturierte Daten korrekt?
   - Confidence Scores angezeigt?
```

### Dokumenten-Suche
```
1. browser_navigate("http://localhost:80/documents")
2. browser_type(search_ref, "Rechnung 2024")
3. browser_press_key("Enter")
4. browser_snapshot → Suchergebnisse analysieren:
   - Relevante Dokumente gefunden?
   - Highlighting korrekt?
   - Pagination funktional?
```

### Display Mode Tests
```
FUER JEDEN Mode (dark, light, whitescreen, blackscreen):
1. browser_click(theme_toggle_ref)
2. browser_screenshot(path="/tmp/mode_[name].png")
3. browser_evaluate("getComputedStyle(document.body).backgroundColor")
4. Farben validieren
```

### Deutsche Zeichensaetze
```
KRITISCH fuer Ablage-System:
1. Eingabe: "Müller-Strauß GmbH & Co. KG"
2. Eingabe: "€1.234,56"
3. Eingabe: "Größenordnung: 5²m"
4. Pruefen: Korrekte Darstellung UND Speicherung
```

## Anti-Patterns (Was NICHT tun)

1. **NICHT** blind auf Elemente klicken ohne vorherigen Snapshot
2. **NICHT** feste Wartezeiten ohne networkidle
3. **NICHT** Screenshots STATT Snapshots fuer Selektoren nutzen
4. **NICHT** Tests ohne Error Handling schreiben
5. **NICHT** Accessibility Tree Struktur ignorieren

## Troubleshooting

### Browser startet nicht
```bash
# Playwright Browser installieren
npx playwright install chromium
```

### MCP Server antwortet nicht
```bash
# Server Status pruefen
npx @playwright/mcp@latest --help

# Mit Debug-Logging starten
DEBUG=pw:* npx @playwright/mcp@latest
```

### Elemente nicht findbar
```
1. browser_wait(2000) → Kurz warten
2. browser_snapshot → Aktuellen State pruefen
3. browser_screenshot → Visuell verifizieren
4. Richtigen ref-Wert nutzen
```

## Metriken & KPIs

Nach jedem vollstaendigen Test-Durchlauf dokumentieren:

| Metrik | Wert |
|--------|------|
| Getestete Routes | X |
| Getestete Formulare | X |
| Screenshots erstellt | X |
| Fehler gefunden | X |
| Kritische Fehler | X |
| Test-Dauer | X min |

## Integration mit CI/CD

Fuer automatisierte Tests in GitHub Actions:

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start Services
        run: docker-compose up -d
      - name: Run Playwright Tests
        run: npx playwright test
      - name: Upload Screenshots
        uses: actions/upload-artifact@v4
        with:
          name: screenshots
          path: test-results/
```

## Referenzen

- [Playwright MCP Server (Microsoft)](https://github.com/microsoft/playwright-mcp)
- [Playwright Dokumentation](https://playwright.dev/docs/intro)
- [Accessibility Tree API](https://playwright.dev/docs/accessibility-testing)
