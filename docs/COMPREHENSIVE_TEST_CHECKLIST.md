# 🧪 Ablage-System Comprehensive Test Checklist

> Automatisierte Tests für **jede Seite**, **jedes Feature**, **jeden Button**
> Mit Screenshots von **allem**

## 📋 Übersicht

| Kategorie | Anzahl Seiten | Status |
|-----------|---------------|--------|
| Auth | 2 | ⬜ |
| Main Pages | 9 | ⬜ |
| Documents | 1 | ⬜ |
| Kassenbuch | 1 | ⬜ |
| Spesen | 1 | ⬜ |
| Streckengeschäft | 2 | ⬜ |
| Finanzen | 3 | ⬜ |
| Kunden | 1 | ⬜ |
| Lieferanten | 1 | ⬜ |
| Personal | 1 | ⬜ |
| Business Entities | 1 | ⬜ |
| Privat | 7 | ⬜ |
| Admin Main | 5 | ⬜ |
| Admin OCR | 3 | ⬜ |
| Admin DATEV | 5 | ⬜ |
| Admin Mahnungen | 7 | ⬜ |
| Admin Banking | 7 | ⬜ |
| **GESAMT** | **57** | ⬜ |

---

## 🔐 Auth Routes (Public)

- [ ] `/login` - Login-Seite
  - [ ] Screenshot: Initial
  - [ ] Form: Email-Feld
  - [ ] Form: Passwort-Feld
  - [ ] Button: Submit
  - [ ] Screenshot: Filled
  - [ ] Test: Error states
  
- [ ] `/forgot-password` - Passwort vergessen
  - [ ] Screenshot: Initial
  - [ ] Form: Email-Feld
  - [ ] Button: Submit

---

## 🏠 Main Pages (Authenticated)

- [ ] `/` - Dashboard/Home
  - [ ] Screenshot: Initial
  - [ ] Widgets testen
  - [ ] Stats testen
  - [ ] Quick-Actions testen

- [ ] `/upload` - Dokument-Upload
  - [ ] Screenshot: Initial
  - [ ] File-Input testen
  - [ ] Drag-and-Drop Zone
  - [ ] Upload mit Test-Dokument
  - [ ] Screenshot: Processing

- [ ] `/search` - Suche
  - [ ] Screenshot: Initial
  - [ ] Search-Input
  - [ ] Filter-Dropdowns
  - [ ] Screenshot: Results

- [ ] `/chat` - Chat/RAG
  - [ ] Screenshot: Initial
  - [ ] Chat-Input
  - [ ] Message-History

- [ ] `/relationships` - Beziehungs-Graph
  - [ ] Screenshot: Initial
  - [ ] Graph-Ansicht
  - [ ] Zoom/Pan

- [ ] `/monitoring` - System-Monitoring
  - [ ] Screenshot: Initial
  - [ ] Stats-Cards
  - [ ] Charts

- [ ] `/jobs` - Jobs
  - [ ] Screenshot: Initial
  - [ ] Job-Liste
  - [ ] Status-Filters

- [ ] `/automation` - Automatisierung
  - [ ] Screenshot: Initial
  - [ ] Rule-Liste
  - [ ] Create-Button

- [ ] `/validation-queue` - Validierungs-Queue
  - [ ] Screenshot: Initial
  - [ ] Queue-Items
  - [ ] Approve/Reject Buttons

---

## 📁 Document Management

- [ ] `/document-groups` - Dokumentengruppen
  - [ ] Screenshot: Initial
  - [ ] Group-Liste
  - [ ] Create-Button

---

## 💰 Kassenbuch

- [ ] `/kasse` - Kassenbuch-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Register-Liste
  - [ ] Create-Register Button
  - [ ] Entry-Liste
  - [ ] New-Entry Dialog
  - [ ] Screenshot: Form filled

---

## 📊 Spesen (Expense Reports)

- [ ] `/spesen` - Spesenübersicht
  - [ ] Screenshot: Initial
  - [ ] Report-Liste
  - [ ] New-Report Dialog
  - [ ] Form: Titel
  - [ ] Form: Zeitraum
  - [ ] Screenshot: Form filled

---

## 🚚 Streckengeschäft

- [ ] `/streckengeschaeft` - Übersicht
  - [ ] Screenshot: Initial
  - [ ] Classification-Liste
  - [ ] Status-Filter

- [ ] `/streckengeschaeft/zm` - ZM-Ansicht
  - [ ] Screenshot: Initial

---

## 💹 Finanzen

- [ ] `/finanzen` - Finanz-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Jahr-Auswahl
  - [ ] Kategorie-Navigation

- [ ] `/finanzen/2025` - Jahr 2025
  - [ ] Screenshot: Initial
  - [ ] Monats-Übersicht
  - [ ] Kategorie-Cards

- [ ] `/finanzen/2024` - Jahr 2024
  - [ ] Screenshot: Initial

---

## 👥 Kunden

- [ ] `/kunden` - Kunden-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Kunden-Liste
  - [ ] Create-Button
  - [ ] Search/Filter

---

## 📦 Lieferanten

- [ ] `/lieferanten` - Lieferanten-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Lieferanten-Liste
  - [ ] Create-Button

---

## 👔 Personal

- [ ] `/personal` - Personal-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Mitarbeiter-Liste
  - [ ] Create-Button

---

## 🏢 Business Entities

- [ ] `/business-entities` - Entities-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Entity-Liste

---

## 🏠 Privat (Private Documents)

- [ ] `/privat` - Privat-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Kategorie-Navigation

- [ ] `/privat/fahrzeuge` - Fahrzeuge
  - [ ] Screenshot: Initial
  - [ ] Fahrzeug-Liste

- [ ] `/privat/finanzen` - Private Finanzen
  - [ ] Screenshot: Initial

- [ ] `/privat/fristen` - Fristen
  - [ ] Screenshot: Initial
  - [ ] Fristen-Kalender

- [ ] `/privat/immobilien` - Immobilien
  - [ ] Screenshot: Initial

- [ ] `/privat/notfall` - Notfall-Dokumente
  - [ ] Screenshot: Initial

- [ ] `/privat/versicherungen` - Versicherungen
  - [ ] Screenshot: Initial

---

## ⚙️ Admin - Main

- [ ] `/admin` - Admin-Dashboard
  - [ ] Screenshot: Initial
  - [ ] Stats-Overview
  - [ ] Quick-Actions

- [ ] `/admin/users` - Benutzerverwaltung
  - [ ] Screenshot: Initial
  - [ ] User-Liste
  - [ ] Create-Button
  - [ ] Edit-Dialog

- [ ] `/admin/settings` - Einstellungen
  - [ ] Screenshot: Initial
  - [ ] Settings-Form
  - [ ] Theme-Toggle
  - [ ] Save-Button

- [ ] `/admin/tunes` - Feineinstellungen
  - [ ] Screenshot: Initial

- [ ] `/admin/job-queue` - Job-Queue
  - [ ] Screenshot: Initial
  - [ ] Queue-Status
  - [ ] Job-Liste

---

## 🔍 Admin - OCR

- [ ] `/admin/ocr-review` - OCR-Review
  - [ ] Screenshot: Initial
  - [ ] Review-Queue

- [ ] `/admin/ocr-training` - OCR-Training
  - [ ] Screenshot: Initial
  - [ ] Training-Batches

- [ ] `/admin/ocr-backends` - OCR-Backends
  - [ ] Screenshot: Initial
  - [ ] Backend-Liste
  - [ ] Status-Anzeige

---

## 📑 Admin - DATEV

- [ ] `/admin/datev` - DATEV-Übersicht
  - [ ] Screenshot: Initial

- [ ] `/admin/datev/config` - DATEV-Konfiguration
  - [ ] Screenshot: Initial
  - [ ] Config-Form

- [ ] `/admin/datev/export` - DATEV-Export
  - [ ] Screenshot: Initial
  - [ ] Date-Range Selector
  - [ ] Export-Button

- [ ] `/admin/datev/history` - DATEV-History
  - [ ] Screenshot: Initial
  - [ ] Export-Liste

- [ ] `/admin/datev/vendors` - DATEV-Vendors
  - [ ] Screenshot: Initial
  - [ ] Vendor-Mapping

---

## 📧 Admin - Mahnungen

- [ ] `/admin/mahnungen` - Mahnwesen-Übersicht
  - [ ] Screenshot: Initial
  - [ ] Stats-Dashboard

- [ ] `/admin/mahnungen/aktiv` - Aktive Mahnungen
  - [ ] Screenshot: Initial
  - [ ] Mahnungs-Liste

- [ ] `/admin/mahnungen/aufgaben` - Aufgaben
  - [ ] Screenshot: Initial
  - [ ] Task-Liste

- [ ] `/admin/mahnungen/einstellungen` - Einstellungen
  - [ ] Screenshot: Initial
  - [ ] Settings-Form
  - [ ] Mahnstufen-Config

- [ ] `/admin/mahnungen/eskalation` - Eskalation
  - [ ] Screenshot: Initial
  - [ ] Eskalations-Rules

- [ ] `/admin/mahnungen/kanban` - Kanban-Board
  - [ ] Screenshot: Initial
  - [ ] Kanban-Columns
  - [ ] Drag-and-Drop

- [ ] `/admin/mahnungen/mahnstopp` - Mahnstopp
  - [ ] Screenshot: Initial
  - [ ] Stopp-Liste

---

## 🏦 Admin - Banking

- [ ] `/admin/banking` - Banking-Übersicht
  - [ ] Screenshot: Initial

- [ ] `/admin/banking/accounts` - Konten
  - [ ] Screenshot: Initial
  - [ ] Konten-Liste
  - [ ] Add-Account

- [ ] `/admin/banking/import` - Import
  - [ ] Screenshot: Initial
  - [ ] File-Upload
  - [ ] Preview

- [ ] `/admin/banking/payments` - Zahlungen
  - [ ] Screenshot: Initial
  - [ ] Payment-Liste

- [ ] `/admin/banking/reconciliation` - Abstimmung
  - [ ] Screenshot: Initial
  - [ ] Match-Interface
  - [ ] Auto-Match Button

- [ ] `/admin/banking/skonto` - Skonto
  - [ ] Screenshot: Initial
  - [ ] Skonto-Rules

- [ ] `/admin/banking/transactions` - Transaktionen
  - [ ] Screenshot: Initial
  - [ ] Transaction-Liste
  - [ ] Filter

---

## 🎨 Feature-Tests

### Document Upload
- [ ] File-Input funktioniert
- [ ] Drag-and-Drop funktioniert
- [ ] Upload-Progress
- [ ] Success-State
- [ ] Error-Handling

### Kasse Entry Creation
- [ ] Dialog öffnet
- [ ] Form validiert
- [ ] Speichern funktioniert
- [ ] Liste aktualisiert

### Spesen Report Creation
- [ ] Dialog öffnet
- [ ] Zeitraum-Auswahl
- [ ] Speichern funktioniert

### Search Functionality
- [ ] Query eingeben
- [ ] Results anzeigen
- [ ] Filter funktionieren
- [ ] Sort funktioniert

### Chat/RAG
- [ ] Message senden
- [ ] Response erhalten
- [ ] Context korrekt

### OCR Backends
- [ ] Status-Check
- [ ] Backend-Details
- [ ] Test-Run

### DATEV Export
- [ ] Config korrekt
- [ ] Export generieren
- [ ] Download funktioniert

### Banking Reconciliation
- [ ] Match-Interface
- [ ] Auto-Match
- [ ] Manual-Match

---

## 📱 Responsive Tests

- [ ] Desktop (1920x1080)
- [ ] Laptop (1366x768)
- [ ] Tablet (768x1024)
- [ ] Mobile (375x812)

---

## 🌓 Theme Tests

- [ ] Light Mode
- [ ] Dark Mode
- [ ] System Preference

---

## ⚠️ Error Handling

- [ ] 404-Seiten
- [ ] API-Errors
- [ ] Network-Errors
- [ ] Validation-Errors

---

## 📸 Screenshot-Kategorien

```
screenshots/comprehensive-test/
├── auth/           # Login, Forgot Password
├── main/           # Dashboard, Upload, Search, etc.
├── documents/      # Document management
├── kasse/          # Kassenbuch
├── spesen/         # Expense reports
├── streckengeschaeft/
├── finanzen/
├── kunden/
├── lieferanten/
├── personal/
├── business-entities/
├── privat/
├── admin/          # All admin pages
├── forms/          # Filled forms
├── modals/         # Dialog screenshots
├── errors/         # Error states
└── interactions/   # Buttons, tabs, tables
```

---

## 🚀 Ausführung

```bash
# Quick Start
npm run test:comprehensive

# Oder direkt
node tests/e2e/comprehensive-test-suite.js

# Windows Batch
run-comprehensive-tests.bat
```

---

## 📊 Erwartete Ergebnisse

- **57+ Seiten** getestet
- **200+ Screenshots** erstellt
- **JSON Report** mit allen Details
- **Markdown Report** für Menschen
- **100% Abdeckung** aller Routes

---

*Erstellt für Ablage-System Comprehensive Testing*
*Version 1.0.0 | 2025-06-30*
