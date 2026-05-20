# Feature-Roadmap Interview - Januar 2026

**Datum:** 01.01.2026
**Interviewer:** Claude (KI-Assistent)
**Interviewpartner:** Projektinhaber
**Ziel:** Identifikation fehlender Features und Priorisierung für Weiterentwicklung

---

## Executive Summary

Das Ablage-System ist bereits eine **funktionsreiche Enterprise-Plattform** mit 47+ API-Endpoints, 29 Frontend-Modulen und 4 OCR-Backends. Basierend auf dem Interview wurden **10 Hauptbereiche** für zukünftige Entwicklung identifiziert.

**Kernphilosophie des Systems:**
> "Zeitersparnis durch KI-Autonomie - aber nur wenn es todsicher und compliant funktioniert"

---

## Priorisierung (Claude's Empfehlung)

### 🔴 P1 - Kritisch (Q1-Q2 2026)

| # | Feature | Begründung | Aufwand |
|---|---------|------------|---------|
| 1 | **Multi-Firma Architektur** | Fundament für alles andere, 2 Firmen bereits aktiv | Hoch |
| 2 | **GoBD-Zertifizierung Basis** | Rechtliche Notwendigkeit für Finanzdokumente | Mittel |
| 3 | **Benachrichtigungssystem Core** | Direkte Zeitersparnis, Kernfeature | Mittel |

### 🟡 P2 - Wichtig (Q2-Q3 2026)

| # | Feature | Begründung | Aufwand |
|---|---------|------------|---------|
| 4 | **Odoo-Integration** | Firma 1 bereits auf Odoo, Realtime-Sync gewünscht | Hoch |
| 5 | **Dashboard & KPIs** | Business-Übersicht fehlt komplett | Mittel |
| 6 | **E-Mail/Ordner-Import** | Automatisierung des Dokumenten-Eingangs | Mittel |
| 7 | **KI-Autonomie erweitern** | Kernwert des Systems | Mittel |

### 🟢 P3 - Nice-to-Have (Q4 2026+)

| # | Feature | Begründung | Aufwand |
|---|---------|------------|---------|
| 8 | **Report-Builder** | Nützlich aber nicht kritisch | Mittel |
| 9 | **Workflow-Automation** | Komplex, braucht solide Basis | Hoch |
| 10 | **Mobile PWA** | "Nice to have" laut Interview | Niedrig |

---

## Detaillierte Feature-Spezifikationen

---

### 1. 🏢 Multi-Firma Architektur

**Status:** Existiert rudimentär, nicht ausgereift
**Priorität:** P1 - Kritisch
**Aufwand:** Hoch (4-6 Wochen)

#### Aktuelle Situation
- 2 Firmen: "Spargelmesser" und "Folie"
- Kunden sind nach Firmen unterteilt
- Benutzer sind pro Firma, aber Switching gewünscht
- Kunden/Lieferanten sind oft firmenübergreifend gleich

#### Anforderungen

```
┌─────────────────────────────────────────────────────────────┐
│                    Multi-Tenant Architektur                  │
├─────────────────────────────────────────────────────────────┤
│  Shared Data Layer                                          │
│  ├─ Kunden (firmenübergreifend)                            │
│  ├─ Lieferanten (firmenübergreifend)                       │
│  └─ Produkte (optional shared)                              │
├─────────────────────────────────────────────────────────────┤
│  Tenant-Specific Data                                       │
│  ├─ Dokumente (gehören zu einer Firma)                     │
│  ├─ Rechnungen                                              │
│  ├─ Buchungen                                               │
│  └─ Benutzer-Zuweisungen                                   │
├─────────────────────────────────────────────────────────────┤
│  Cross-Tenant Features                                      │
│  ├─ Firmen-Switcher im Header                              │
│  ├─ Firmenübergreifende Auswertungen                       │
│  └─ Konsolidierte Reports                                   │
└─────────────────────────────────────────────────────────────┘
```

#### Technische Umsetzung

1. **Datenbank-Schema:**
   - `tenant_id` auf allen relevanten Tabellen
   - Shared-Tables für Stammdaten (mit Tenant-Override-Möglichkeit)
   - Row-Level Security in PostgreSQL

2. **API-Layer:**
   - Tenant-Context in JWT-Token
   - Middleware für automatische Filterung
   - Endpoint für Tenant-Switch

3. **Frontend:**
   - Firmen-Switcher Komponente
   - Persistenz der Auswahl
   - Visuelle Unterscheidung (Farbe/Logo pro Firma)

#### Skalierung
- Aktuell: 2 Firmen
- Geplant: 3-4 in Zukunft
- Architektur muss N Firmen unterstützen

---

### 2. 📋 GoBD-Zertifizierung

**Status:** Teilweise implementiert (Audit-Logs, Kassenbuch)
**Priorität:** P1 - Kritisch
**Aufwand:** Mittel (3-4 Wochen)

#### Anforderungen für GoBD-Konformität

| Anforderung | Status | Aktion |
|-------------|--------|--------|
| Nachvollziehbarkeit | ✅ Audit-Logs | Erweitern |
| Nachprüfbarkeit | ⚠️ Teilweise | Verfahrensdoku |
| Unveränderbarkeit | ⚠️ Teilweise | Signatur-System |
| Vollständigkeit | ✅ Vorhanden | - |
| Ordnung | ✅ Strukturiert | - |
| Zeitgerechte Buchung | ⚠️ Teilweise | Automatisieren |
| Aufbewahrung | ❌ Fehlt | Implementieren |

#### Zu implementieren

1. **Verfahrensdokumentation (Auto-generiert):**
   ```markdown
   - Systembeschreibung
   - Datenflüsse
   - Berechtigungskonzept
   - Archivierungsregeln
   - Änderungshistorie
   ```

2. **Revisionssichere Archivierung:**
   - Zeitstempel-Signatur (qualifiziert oder Blockchain-Hash)
   - Unveränderlichkeit nach Archivierung
   - Prüfsummen für alle Dokumente

3. **Aufbewahrungsfristen-Management:**
   ```
   Admin-Einstellungen:
   ├─ Automatische Warnung vor Löschung: [x] An/Aus
   ├─ Warnzeitraum: [30] Tage vor Ablauf
   ├─ Automatische Löschung: [x] An/Aus
   └─ Standard-Aufbewahrungsfrist: [10] Jahre
   ```

4. **Steuerberater-Zugang:**
   - Eigene Rolle "Steuerberater"
   - Read-Only auf Finanzdokumente
   - Export-Berechtigung
   - Zeitlich begrenzbar

---

### 3. 🔔 Intelligentes Benachrichtigungssystem

**Status:** Basis vorhanden, nicht ausgebaut
**Priorität:** P1 - Kritisch
**Aufwand:** Mittel (3-4 Wochen)

#### Dreistufige Hierarchie

```
┌─────────────────────────────────────────────────────────────┐
│  Ebene 1: System-Defaults                                   │
│  └─ Basis-Regeln für alle (Admin konfiguriert)             │
├─────────────────────────────────────────────────────────────┤
│  Ebene 2: Rolle/Department                                  │
│  └─ Spezifische Regeln pro Gruppe (Admin konfiguriert)     │
├─────────────────────────────────────────────────────────────┤
│  Ebene 3: User-Präferenzen                                  │
│  └─ Individuelle Anpassungen (User selbst)                 │
└─────────────────────────────────────────────────────────────┘
```

#### Benachrichtigungs-Typen

| Kategorie | Beispiele |
|-----------|-----------|
| **Zahlungen** | Überfällig, Skonto läuft ab, Mahnung fällig |
| **Verträge** | Kündigung, Verlängerung, Ablauf |
| **Lieferungen** | Lieferant liefert bald, Verzögerung |
| **Steuern** | USt-Voranmeldung, Fristen |
| **Dokumente** | Neue Dokumente, Validierung ausstehend |
| **System** | Fehler, Warnungen, Wartung |

#### Kanäle (alle konfigurierbar)

- ✅ In-App Dashboard Widget
- ✅ E-Mail (Digest oder Sofort)
- ✅ Browser Push-Notifications
- ✅ Slack Integration
- ✅ Microsoft Teams Integration
- ⬜ Mobile Push (später mit PWA)

#### Regel-Engine

```python
# Beispiel-Regel
{
    "name": "Mahnung fällig",
    "trigger": {
        "type": "rechnung_ueberfaellig",
        "tage": 14
    },
    "bedingungen": [
        {"feld": "betrag", "operator": ">", "wert": 100},
        {"feld": "kunde.mahnsperre", "operator": "!=", "wert": True}
    ],
    "aktionen": [
        {"typ": "benachrichtigung", "kanal": ["email", "slack"]},
        {"typ": "aufgabe_erstellen", "zuweisen": "buchhaltung"}
    ],
    "empfaenger": {
        "rollen": ["buchhaltung", "geschaeftsfuehrung"],
        "departments": ["finanzen"]
    }
}
```

---

### 4. 🔗 Odoo-Integration

**Status:** Nicht vorhanden
**Priorität:** P2 - Wichtig
**Aufwand:** Hoch (4-5 Wochen)

#### Kontext
- Firma 1 bereits auf Odoo (Cloud)
- Firma 2 Migration geplant (nächste Jahre)
- Realtime oder mindestens tägliche Sync gewünscht

#### Bidirektionale Synchronisation

```
┌─────────────────┐                    ┌─────────────────┐
│     ODOO        │ ◄──── Sync ────►   │  Ablage-System  │
├─────────────────┤                    ├─────────────────┤
│ Rechnungen      │ ──────────────────► │ Dokumente      │
│ Angebote        │ ──────────────────► │ Extrahierte    │
│ Bestellungen    │ ──────────────────► │ Daten          │
├─────────────────┤                    ├─────────────────┤
│ Kunden          │ ◄────────────────► │ Kunden         │
│ Lieferanten     │ ◄────────────────► │ Lieferanten    │
├─────────────────┤                    ├─────────────────┤
│ Zahlungsstatus  │ ◄────────────────── │ Banking-Match  │
│ Dokument-Links  │ ◄────────────────── │ Archiv-URLs    │
└─────────────────┘                    └─────────────────┘
```

#### Technische Umsetzung

1. **Odoo REST API Connector:**
   ```python
   class OdooConnector(ERPConnector):
       async def sync_invoices(self, since: datetime) -> List[Invoice]
       async def sync_customers(self) -> List[Customer]
       async def update_payment_status(self, invoice_id, status)
       async def attach_document(self, record_id, document_url)
   ```

2. **Sync-Modi:**
   - Realtime: Webhooks von Odoo
   - Scheduled: Cron-Job alle 15 Minuten
   - Manual: On-Demand Sync

3. **Konflikt-Handling:**
   - Last-Write-Wins mit Audit-Log
   - Oder: Conflict-Queue für manuelle Auflösung

#### ERP-Agnostische Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    ERP Connector Layer                       │
├─────────────────────────────────────────────────────────────┤
│  Interface: ERPConnector                                    │
│  ├─ sync_documents()                                        │
│  ├─ sync_customers()                                        │
│  ├─ sync_suppliers()                                        │
│  └─ update_status()                                         │
├──────────┬──────────┬──────────┬───────────────────────────┤
│  Odoo    │  Lexware │   CSV    │  Future: SAP, etc.        │
│  Plugin  │  Export  │  Import  │                           │
└──────────┴──────────┴──────────┴───────────────────────────┘
```

---

### 5. 📊 Dashboard & KPIs

**Status:** Basis-Monitoring vorhanden, kein Business-Dashboard
**Priorität:** P2 - Wichtig
**Aufwand:** Mittel (3-4 Wochen)

#### Widget-Katalog

| Widget | Beschreibung | Berechtigung |
|--------|--------------|--------------|
| 💰 Offene Posten | Überfällige Rechnungen, Summen, Aging | Finanzen |
| 📊 Cashflow | Einnahmen/Ausgaben Trend | Finanzen |
| 📄 Dokumente heute | Neu, verarbeitet, wartend | Alle |
| 🔔 Erinnerungen | Anstehende Fristen | Alle |
| 📈 Lieferanten-KPI | Pünktlichkeit, Qualität | Einkauf |
| 🏢 Firmen-Übersicht | Kennzahlen pro Firma | GF |
| ⚡ OCR-Status | Queue, Erfolgsrate | Admin |
| 🎯 Validierung | Offene Reviews | Validierung |

#### Filter-Engine (Power-BI-artig)

```
┌─────────────────────────────────────────────────────────────┐
│  Filter-Konfiguration                                       │
├─────────────────────────────────────────────────────────────┤
│  Zeitraum A: [01.01.2025] - [31.03.2025]     [Vergleichen] │
│  Zeitraum B: [01.01.2024] - [31.03.2024]                   │
├─────────────────────────────────────────────────────────────┤
│  Firma:      [x] Spargelmesser  [x] Folie  [ ] Alle        │
│  Kategorie:  [Mehrfachauswahl Dropdown]                    │
│  Lieferant:  [Mehrfachauswahl mit Suche]                   │
│  Betrag:     [Von: ___] [Bis: ___]                         │
│  Custom:     [+ Filter hinzufügen]                         │
└─────────────────────────────────────────────────────────────┘
```

#### Berechtigungs-System

```yaml
rollen:
  geschaeftsfuehrung:
    widgets: [alle]
  buchhaltung:
    widgets: [offene_posten, cashflow, dokumente, erinnerungen]
  mitarbeiter:
    widgets: [dokumente, erinnerungen]

departments:
  finanzen:
    zusaetzliche_widgets: [umsatzsteuer, datev_status]
```

#### Personalisierung

- Drag & Drop Widget-Anordnung
- Widget-Größe anpassbar
- Eigene Filter-Presets speichern
- Dashboard-Layouts speichern/laden

---

### 6. 📧 E-Mail & Ordner-Import

**Status:** Nicht vorhanden
**Priorität:** P2 - Wichtig
**Aufwand:** Mittel (2-3 Wochen)

#### E-Mail-Import

```
┌─────────────────────────────────────────────────────────────┐
│  E-Mail Inbox Konfiguration (Admin)                         │
├─────────────────────────────────────────────────────────────┤
│  Firma: [Spargelmesser ▼]                                   │
├─────────────────────────────────────────────────────────────┤
│  IMAP Server:    [imap.example.com]                         │
│  Port:           [993]  [x] SSL                             │
│  Benutzer:       [rechnung@spargelmesser.de]                │
│  Passwort:       [••••••••••]                               │
├─────────────────────────────────────────────────────────────┤
│  Abruf-Intervall: [5] Minuten                               │
│  Ziel-Ordner:     [Eingangsrechnungen ▼]                    │
├─────────────────────────────────────────────────────────────┤
│  KI-Filter:                                                 │
│  [x] Spam/Nicht-Rechnungen automatisch ignorieren           │
│  [x] Duplikate erkennen und warnen                          │
│  [x] Absender-Whitelist aktivieren                          │
└─────────────────────────────────────────────────────────────┘
```

#### Multi-Firma E-Mail

- Jede Firma kann eigene E-Mail-Postfächer haben
- Admin konfiguriert pro Firma
- Automatische Zuordnung zur richtigen Firma

#### Ordner-Watcher

```
┌─────────────────────────────────────────────────────────────┐
│  Ordner-Watcher Konfiguration                               │
├─────────────────────────────────────────────────────────────┤
│  [+ Neuen Ordner hinzufügen]                                │
├─────────────────────────────────────────────────────────────┤
│  1. \\server\scans\eingang                                  │
│     Firma: Spargelmesser | Kategorie: Auto-Detect          │
│     Status: ✅ Aktiv | Letzte Prüfung: vor 2 Min           │
│     [Bearbeiten] [Pausieren] [Löschen]                      │
├─────────────────────────────────────────────────────────────┤
│  2. C:\Lexware\Export\Rechnungen                            │
│     Firma: Folie | Kategorie: Ausgangsrechnung              │
│     Status: ✅ Aktiv | Letzte Prüfung: vor 1 Min           │
│     [Bearbeiten] [Pausieren] [Löschen]                      │
└─────────────────────────────────────────────────────────────┘
```

#### Verarbeitung

1. Datei erkannt → In Queue
2. Duplikat-Check (Hash-basiert)
3. KI-Klassifizierung (Dokument-Typ)
4. OCR-Pipeline
5. Firma-Zuordnung (aus Ordner-Config oder KI)
6. Benachrichtigung bei Erfolg/Fehler

---

### 7. 🤖 KI-Autonomie erweitern

**Status:** Gute Basis, Erweiterung gewünscht
**Priorität:** P2 - Wichtig
**Aufwand:** Mittel (ongoing)

#### Confidence-basierte Autonomie

```
┌─────────────────────────────────────────────────────────────┐
│  Konfidenz-Schwellen (Admin-konfigurierbar)                 │
├─────────────────────────────────────────────────────────────┤
│  95%+ ──► Automatisch verarbeiten                           │
│           └─ Audit-Log: "KI-Entscheidung"                   │
│                                                             │
│  80-95% ─► Vorschlag mit 1-Click Bestätigung               │
│           └─ User sieht: "KI schlägt vor: [X]"             │
│                                                             │
│  <80% ───► Manuelle Review Queue                            │
│           └─ User muss aktiv entscheiden                    │
└─────────────────────────────────────────────────────────────┘
```

#### Neue KI-Features

| Feature | Beschreibung | Konfidenz-Ziel |
|---------|--------------|----------------|
| Auto-Kategorisierung | Dokument-Typ erkennen | 95%+ |
| Auto-Kontierung | Buchungskonto vorschlagen | 90%+ |
| Smart Matching | Rechnung ↔ Lieferschein ↔ Bestellung | 95%+ |
| Anomalie-Erkennung | Ungewöhnliche Beträge/Muster | 85%+ |
| Zahlungs-Vorhersage | "Kunde zahlt in ~X Tagen" | 80%+ |
| Duplikat-Erkennung | Ähnliche Dokumente finden | 90%+ |

#### Self-Learning Loop

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ KI      │ →  │ User    │ →  │Korrektur│ →  │ Training│
│Vorschlag│    │ prüft   │    │ speichern│   │ Update  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
                                                  ↓
                                            Bessere
                                            Vorhersagen
```

#### Compliance-Garantie

- Jede KI-Entscheidung wird geloggt
- Audit-Trail: Wer/Was/Wann/Warum
- Rollback-Möglichkeit
- Explainable AI: "Warum hat die KI X entschieden?"

---

### 8. 📑 Report-Builder

**Status:** Export vorhanden, kein Builder
**Priorität:** P3 - Nice-to-Have
**Aufwand:** Mittel (3-4 Wochen)

#### Universelle Templates (99% Abdeckung für SMEs)

| Report | Beschreibung | Format |
|--------|--------------|--------|
| Offene Posten | Übersicht aller unbezahlten Rechnungen | PDF/Excel |
| Eingangsrechnungen | Monatlich nach Lieferant | PDF/Excel |
| Ausgangsrechnungen | Monatlich nach Kunde | PDF/Excel |
| USt-Vorbereitung | Für Steuerberater | PDF/Excel |
| Lieferanten-Analyse | Performance, Volumen | PDF/Excel |
| Kunden-Analyse | Umsatz, Zahlungsverhalten | PDF/Excel |
| Cashflow-Report | Ein-/Ausgaben über Zeit | PDF/Excel |
| Dokumenten-Statistik | Volumen, OCR-Qualität | PDF |
| Vertrags-Übersicht | Laufzeiten, Kündigungsfristen | PDF/Excel |

#### Custom Report Builder

```
┌─────────────────────────────────────────────────────────────┐
│  Report erstellen                                           │
├─────────────────────────────────────────────────────────────┤
│  Name: [Mein Custom Report]                                 │
├─────────────────────────────────────────────────────────────┤
│  Datenquelle: [Eingangsrechnungen ▼]                        │
├─────────────────────────────────────────────────────────────┤
│  Spalten:                                                   │
│  [x] Datum  [x] Lieferant  [x] Betrag  [ ] Kategorie       │
│  [x] Status [x] Zahlungsziel  [ ] Notizen                  │
├─────────────────────────────────────────────────────────────┤
│  Gruppierung: [Lieferant ▼]                                 │
│  Sortierung:  [Datum ▼] [Absteigend]                        │
├─────────────────────────────────────────────────────────────┤
│  Filter: [Zeitraum: Letzter Monat] [Betrag > 1000€]        │
├─────────────────────────────────────────────────────────────┤
│  [Als Template speichern]  [Vorschau]  [Exportieren]        │
└─────────────────────────────────────────────────────────────┘
```

#### Scheduled Exports

```yaml
scheduled_reports:
  - name: "Wöchentliche Offene Posten"
    template: "offene_posten"
    schedule: "0 8 * * MON"  # Montag 8:00
    format: "pdf"
    empfaenger:
      - buchhaltung@firma.de
      - chef@firma.de

  - name: "Monatlicher Lieferanten-Report"
    template: "lieferanten_analyse"
    schedule: "0 9 1 * *"  # 1. des Monats
    format: "excel"
    empfaenger:
      - einkauf@firma.de
```

#### Externe Empfänger

- E-Mail-Versand an beliebige Adressen
- Passwort-geschützte PDFs (optional)
- Download-Link statt Attachment (für große Files)
- Steuerberater als fester Empfänger konfigurierbar

---

### 9. ⚙️ Workflow-Automation

**Status:** Basis-Modul vorhanden
**Priorität:** P3 - Nice-to-Have
**Aufwand:** Hoch (5-6 Wochen)

#### Visueller Regel-Editor

```
┌─────────────────────────────────────────────────────────────┐
│  Regel erstellen                                            │
├─────────────────────────────────────────────────────────────┤
│  Name: [Große Rechnungen zur Freigabe]                      │
├─────────────────────────────────────────────────────────────┤
│  WENN                                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [Dokument-Typ ▼] [ist ▼] [Eingangsrechnung ▼]       │   │
│  │ [+ UND]                                              │   │
│  │ [Betrag ▼] [größer als ▼] [10000] [€]               │   │
│  │ [+ UND]                                              │   │
│  │ [Lieferant ▼] [ist nicht ▼] [Freigegeben ▼]         │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  DANN                                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [1] [Benachrichtigen ▼] [Geschäftsführung ▼]        │   │
│  │ [2] [Tag setzen ▼] [Freigabe erforderlich]          │   │
│  │ [3] [Workflow starten ▼] [Freigabe-Prozess ▼]       │   │
│  │ [+ Aktion hinzufügen]                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### Verfügbare Bedingungen

| Kategorie | Bedingungen |
|-----------|-------------|
| Dokument | Typ, Status, Datum, Alter |
| Betrag | Wert, Währung, Vergleich |
| Partner | Kunde, Lieferant, Neu/Bekannt |
| Zeit | Wochentag, Uhrzeit, Frist |
| OCR | Konfidenz, Backend, Fehler |
| Custom | Beliebige Feldwerte |

#### Verfügbare Aktionen

| Aktion | Beschreibung |
|--------|--------------|
| Benachrichtigen | User/Rolle/Department informieren |
| Tag setzen | Label hinzufügen |
| Ordner verschieben | In anderen Ordner |
| Freigabe starten | Approval-Workflow |
| Export | DATEV, E-Mail, etc. |
| Webhook | Externes System triggern |
| Aufgabe erstellen | Task für User |
| Eskalieren | Nach X Tagen eskalieren |

#### Workflow-Ketten

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Eingang │ →  │ OCR &   │ →  │ Auto-   │ →  │Ablage   │
│         │    │ Validier│    │ Kontier │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
                    │              │
                    ▼              ▼
              ┌─────────┐    ┌─────────┐
              │ Review  │    │Freigabe │
              │ Queue   │    │ nötig?  │
              └─────────┘    └─────────┘
```

#### Berechtigungen

- Admins: Alle Regeln erstellen/bearbeiten
- Power-User: Eigene Regeln mit Einschränkungen
- Genehmigungs-Workflow für kritische Regeln

---

### 10. 📱 Mobile PWA

**Status:** Nicht vorhanden
**Priorität:** P3 - Nice-to-Have
**Aufwand:** Niedrig-Mittel (2-3 Wochen)

#### Features

| Feature | Beschreibung |
|---------|--------------|
| 📸 Foto-Upload | Beleg fotografieren → direkt hochladen |
| 📄 Quick-View | Dokumente unterwegs einsehen |
| ✅ Validierung | Review-Queue abarbeiten |
| 🔔 Push | Erinnerungen aufs Handy |
| 📊 Dashboard | KPIs mobil checken |
| 🔍 Suche | Dokumente finden |

#### Technische Umsetzung

- Progressive Web App (PWA)
- Responsive Design (bereits 4 Display-Modi)
- Service Worker für Offline-Fähigkeit
- Push-Notifications API
- Camera API für Foto-Upload

#### Offline-Modus

- Zuletzt angesehene Dokumente gecacht
- Queue für Uploads wenn offline
- Sync bei Verbindung

---

## Zusammenfassung der Interview-Erkenntnisse

### Strategische Entscheidungen

1. **ERP-Strategie:**
   - Lexware ist Auslaufmodell (closed system)
   - Odoo ist die Zukunft (Cloud, offene API)
   - System muss ERP-agnostisch sein

2. **Multi-Firma:**
   - 1 System mit Multi-Tenant (nicht 2 getrennte)
   - Shared Stammdaten, getrennte Dokumente
   - Skalierbar auf 3-4+ Firmen

3. **KI-Philosophie:**
   - Maximale Autonomie bei garantierter Zuverlässigkeit
   - Confidence-basierte Entscheidungen
   - 100% Audit-Trail für Compliance

4. **Konfigurations-Philosophie:**
   - "So konfigurierbar wie möglich"
   - Aber: Was gebaut wird, muss todsicher funktionieren
   - Dreistufig: System → Rolle/Department → User

### Nicht-Ziele (bewusst ausgeschlossen)

- ❌ Dokumenten-Erstellung (bleibt in Lexware/Odoo)
- ❌ Plugin-Marketplace (zu früh)
- ❌ Native Mobile App (PWA reicht)

### Erfolgskriterien

1. **Zeitersparnis** als Kernmetrik
2. **Compliance** (GoBD-Zertifizierung)
3. **Zuverlässigkeit** (todsicher)
4. **Flexibilität** (hochkonfigurierbar)

---

## Nächste Schritte

### Sofort (Januar 2026)
1. [ ] Multi-Firma Architektur-Design finalisieren
2. [ ] GoBD-Anforderungen detailliert dokumentieren
3. [ ] Benachrichtigungs-System Prototyp

### Q1 2026
4. [ ] Multi-Firma Implementation
5. [ ] GoBD-Basis (Aufbewahrung, Signatur)
6. [ ] Benachrichtigungs-System Core

### Q2 2026
7. [ ] Odoo-Connector Entwicklung
8. [ ] Dashboard & KPIs
9. [ ] E-Mail/Ordner-Import

### Q3-Q4 2026
10. [ ] Report-Builder
11. [ ] Workflow-Automation erweitert
12. [ ] Mobile PWA
13. [ ] GoBD-Zertifizierung beantragen

---

*Dokument erstellt: 01.01.2026*
*Basierend auf: Interview-Session mit Projektinhaber*
