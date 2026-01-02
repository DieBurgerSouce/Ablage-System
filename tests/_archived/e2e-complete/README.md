# Ablage-System - Vollständiger E2E Test

## 🚀 Ausführung

```bash
# In das Projektverzeichnis wechseln
cd C:\Users\benfi\Ablage_System

# Test ausführen
node tests/e2e-complete/comprehensive-test.js
```

## 📋 Was wird getestet?

### Seiten (50+ Routen)
- ✅ Alle Hauptseiten (Dashboard, Suche, Upload, Chat, Jobs, Monitoring)
- ✅ Dokumente (Validierung, Gruppen)
- ✅ Kunden & Lieferanten
- ✅ Personal
- ✅ Finanzen
- ✅ Kassenbuch
- ✅ Spesen
- ✅ Streckengeschäft
- ✅ Privat-Bereich (7 Unterseiten)
- ✅ Admin (8+ Seiten)
- ✅ Banking (7 Seiten)
- ✅ DATEV (5 Seiten)
- ✅ Mahnwesen (7 Seiten)

### Features
- ✅ Navigation & Sidebar
- ✅ Suche mit Filtern
- ✅ Upload mit echten Dokumenten
- ✅ Kassenbuch Einträge
- ✅ Spesen Abrechnungen
- ✅ Streckengeschäft
- ✅ Mahnwesen Kanban
- ✅ Banking
- ✅ DATEV
- ✅ Admin-Funktionen

### UI Elemente
- ✅ Alle Buttons
- ✅ Alle Formulare & Inputs
- ✅ Alle Dialoge
- ✅ Alle Tabs
- ✅ Alle Dropdowns

### Responsive Design
- ✅ Desktop (1920x1080)
- ✅ Laptop (1366x768)
- ✅ Tablet (768x1024)
- ✅ Mobile (375x667)

## 📸 Screenshots

Screenshots werden gespeichert in:
```
tests/e2e-complete/screenshots/
├── auth/           # Login Screenshots
├── main/           # Hauptseiten
├── kunden/         # Kunden-Bereich
├── lieferanten/    # Lieferanten-Bereich
├── personal/       # Personal-Bereich
├── finanzen/       # Finanzen-Bereich
├── kasse/          # Kassenbuch
├── spesen/         # Spesen
├── streckengeschaeft/  # Streckengeschäft
├── privat/         # Privat-Bereich
├── admin/          # Admin-Bereich
├── banking/        # Banking
├── datev/          # DATEV
├── mahnungen/      # Mahnwesen
├── documents/      # Dokumente
├── business/       # Business Entities
├── errors/         # Fehler-Screenshots
└── features/
    ├── kasse/
    ├── spesen/
    ├── streckengeschaeft/
    ├── mahnwesen/
    ├── banking/
    ├── datev/
    ├── admin/
    ├── privat/
    ├── upload/
    ├── search/
    ├── navigation/
    └── responsive/
```

## 📊 Reports

Reports werden generiert in:
```
tests/e2e-complete/reports/
├── latest.html     # Aktueller HTML Report
├── latest.json     # Aktueller JSON Report
├── report_TIMESTAMP.html
└── report_TIMESTAMP.json
```

## ⚙️ Konfiguration

Die Konfiguration kann direkt in `comprehensive-test.js` angepasst werden:

```javascript
const CONFIG = {
    baseUrl: 'http://localhost',
    credentials: {
        email: 'admin@localhost.com',
        password: 'admin123'
    },
    screenshotDir: './tests/e2e-complete/screenshots',
    reportDir: './tests/e2e-complete/reports',
    testDocuments: './test_documents',
    timeout: 30000,
    waitAfterNavigation: 1500,
    waitAfterAction: 800
};
```

## 🔧 Voraussetzungen

1. Frontend muss laufen auf localhost:80
2. Backend muss laufen
3. Admin-User muss existieren (admin@localhost.com / admin123)
4. Playwright muss installiert sein: `npm install playwright`

## 📈 Beispiel Ausgabe

```
╔═══════════════════════════════════════════════════════════════════════╗
║     ABLAGE-SYSTEM - VOLLSTÄNDIGER E2E TEST                            ║
╚═══════════════════════════════════════════════════════════════════════╝

🚀 Starte Browser...

═══════════════════════════════════════════════════════════════════════
  📝 SCHRITT 1: LOGIN
═══════════════════════════════════════════════════════════════════════
  ✅ Login erfolgreich

═══════════════════════════════════════════════════════════════════════
  📄 SCHRITT 2: ALLE SEITEN TESTEN
═══════════════════════════════════════════════════════════════════════
  📊 52 Seiten zu testen...

  🔍 Teste: Dashboard (/)
    ✅ Geladen in 342ms
    📊 8 Buttons, 0 Formulare, 2 Inputs
    📸 Screenshot: ./screenshots/main/Dashboard_2025-...png

... (weitere Seiten)

═══════════════════════════════════════════════════════════════════════
  📊 TEST ZUSAMMENFASSUNG
═══════════════════════════════════════════════════════════════════════
  Gesamt:        52
  Bestanden:     50 ✅
  Fehlgeschlagen: 2 ❌
  Erfolgsrate:   96.2%
  Dauer:         127.45s
  Screenshots:   184
```
