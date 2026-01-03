# Ablage-System: Pilot-Readiness-Plan

## Familienhandelsbetrieb (10 Mitarbeiter)

**Ziel:** Komplettes Büro papierlos in einer Woche
**Pilot-Team:** Prokurist, 3 Azubis, Ben (technischer Support)
**Skill-Level:** Smartphone bis Excel (keine IT-Experten)
**Erwartete Einsparung:** ~€7.000/Jahr Arbeitskosten

---

## Teil 1: Die 12 realen Workflows des Büroalltags

### TÄGLICHE WORKFLOWS (Priorität: KRITISCH für Pilot)

#### Workflow 1: Eingangspost verarbeiten (08:00-09:00)
**Wer:** Prokurist / Azubi
**Heute:** Post öffnen → Sortieren → Stempeln → Ordner → Lexware prüfen → StarMoney prüfen → DATEV prüfen → Steuerberaterin anrufen
**Pain Points:**
- 4 verschiedene Programme offen
- Beleg nicht gefunden (häufig!)
- "Wie buche ich das?" - Unsicherheit
- Manueller Abgleich mit Bestellung

**Ablage-System muss können:**
```
[Scannen/Foto] → [Automatische Erkennung] → [Buchungsvorschlag] → [Bestätigen] → [Fertig]
```

**Benötigte Module:**
- ✅ OCR-Service (multi-backend)
- ✅ Dokumentenklassifikation
- ✅ Lieferanten-Erkennung
- ⚠️ Buchungsvorschlag (SKR03/04) - Status prüfen
- ⚠️ Bestellabgleich - Status prüfen

**Erfolgskriterium Pilot:**
- [ ] 30 Eingangsrechnungen pro Tag verarbeiten
- [ ] <2 Minuten pro Beleg (aktuell: ~10 Min)
- [ ] 90% Erkennungsrate ohne manuelle Korrektur

---

#### Workflow 2: "Wo ist...?" - Dokumentensuche (ad-hoc, mehrmals täglich)
**Wer:** Alle
**Heute:** Ordner durchblättern → Excel durchsuchen → Lexware durchsuchen → aufgeben
**Pain Points:**
- Beleg nicht gefunden = Frust + Zeitverlust
- "Hat der Lieferant die Rechnung geschickt?"
- Steuerberaterin fragt nach Beleg → Suche dauert ewig

**Ablage-System muss können:**
```
[Suchfeld] → "Rechnung Müller November" → [Sofort Ergebnisse] → [Dokument öffnen/drucken]
```

**Benötigte Module:**
- ✅ Volltextsuche (pgvector)
- ✅ Filterung (Datum, Lieferant, Betrag, Typ)
- ⚠️ Schnelle Vorschau - Status prüfen
- 🔴 RAG-Chat ("Zeig mir alle Rechnungen über €500 von letztem Monat") - Future

**Erfolgskriterium Pilot:**
- [ ] Jedes Dokument in <10 Sekunden findbar
- [ ] Suche funktioniert auch mit Tippfehlern
- [ ] Filter kombinierbar (Datum + Lieferant + Betrag)

---

#### Workflow 3: Ausgangsrechnungen erstellen & verfolgen
**Wer:** Prokurist
**Heute:** Lexware → Rechnung erstellen → Drucken/Mailen → Manuell notieren → Abgleich ob bezahlt
**Pain Points:**
- Ausgangsrechnungen abgleichen ob bezahlt (manuell!)
- Skonto-Fristen übersehen
- Mahnungen vergessen

**Ablage-System muss können:**
```
[Dashboard] → "3 Rechnungen überfällig" → [Details] → [Mahnung erstellen] → [Versenden]
```

**Benötigte Module:**
- ✅ Mahnwesen (7 Routes vorhanden)
- ✅ Offene-Posten-Verwaltung
- ⚠️ Zahlungseingang-Matching - Status prüfen
- ⚠️ Skonto-Warnung - Status prüfen
- 🔴 E-Rechnungs-Export (ZUGFeRD/XRechnung) - PFLICHT ab 2025!

**Erfolgskriterium Pilot:**
- [ ] Überfällige Rechnungen auf Dashboard sichtbar
- [ ] Ein-Klick-Mahnung funktioniert
- [ ] Automatische Skonto-Frist-Warnung (3 Tage vorher)

---

#### Workflow 4: Zahlungsverkehr / Banking
**Wer:** Prokurist
**Heute:** StarMoney → Kontoauszug → Manuell in Lexware → Zuordnen zu Rechnung → DATEV
**Pain Points:**
- Zahlungseingänge manuell zuordnen
- "Welche Rechnung wurde bezahlt?" - Verwendungszweck oft kryptisch
- Dreifache Dateneingabe (StarMoney, Lexware, DATEV)

**Ablage-System muss können:**
```
[Banking-Import] → [Automatische Zuordnung] → "Zahlung €847 = Rechnung #4521 Müller GmbH" → [Bestätigen]
```

**Benötigte Module:**
- ✅ Banking/FinTS Integration (7 Routes)
- ⚠️ Automatisches Matching Zahlung↔Rechnung - Status prüfen
- ⚠️ MT940/CAMT Import - Status prüfen
- 🔴 Reconciliation-Report - Needs implementation

**Erfolgskriterium Pilot:**
- [ ] Kontoauszug-Import funktioniert
- [ ] 70%+ automatische Zuordnung
- [ ] Manuelle Zuordnung in <30 Sekunden

---

#### Workflow 5: Kassenführung (täglich bei Bargeschäften)
**Wer:** Azubi
**Heute:** Kassensturz → Excel-Kassenbuch → Belege sammeln → Ende Monat zu Steuerberaterin
**Pain Points:**
- Excel ist NICHT GoBD-konform!
- "Auf welche Firma buche ich das?" (Multi-Firma)
- Kassenbestand negativ = Problem bei Prüfung

**Ablage-System muss können:**
```
[Kassenbuch öffnen] → [Einnahme/Ausgabe erfassen] → [Beleg scannen] → [Tagesabschluss]
```

**Benötigte Module:**
- ✅ Kassenbuch (cash_service.py)
- ✅ Multi-Firma-Support (Row-Level Security)
- ⚠️ TSE-Anbindung - Status prüfen (gesetzlich erforderlich!)
- ⚠️ Tagesabschluss-Report - Status prüfen

**Erfolgskriterium Pilot:**
- [ ] Kassenbuch ist GoBD-konform
- [ ] Multi-Firma-Auswahl funktioniert
- [ ] Negativer Bestand wird verhindert
- [ ] Tagesabschluss-PDF generierbar

---

### WÖCHENTLICHE WORKFLOWS (Priorität: WICHTIG)

#### Workflow 6: Offene Posten prüfen (Montags)
**Wer:** Prokurist
**Heute:** Lexware-Liste drucken → Mit Kontoauszug vergleichen → Anrufe bei Kunden
**Pain Points:**
- Keine aktuelle Übersicht
- Wer schuldet uns wie viel?
- Was müssen wir noch zahlen?

**Ablage-System muss können:**
```
[Dashboard] → [Offene Forderungen: €12.450] → [Details] → [Nach Fälligkeit sortiert]
[Dashboard] → [Offene Verbindlichkeiten: €8.200] → [Skonto-Potential: €164]
```

**Benötigte Module:**
- ✅ Offene-Posten-Listen
- ✅ Fälligkeitsübersicht
- ⚠️ Skonto-Potential-Berechnung - Status prüfen
- ⚠️ Aging-Report (30/60/90 Tage) - Status prüfen

---

#### Workflow 7: Zahlungslauf vorbereiten (Mittwoch/Freitag)
**Wer:** Prokurist
**Heute:** Fällige Rechnungen sammeln → Skonto prüfen → SEPA-Datei in StarMoney → Freigabe
**Pain Points:**
- Skonto-Fristen übersehen = Geld verschenkt
- Manuelle SEPA-Datei-Erstellung fehleranfällig

**Ablage-System muss können:**
```
[Zahlungslauf] → [Fällige Rechnungen] → [Skonto optimiert] → [SEPA-Export] → [Fertig]
```

**Benötigte Module:**
- ⚠️ Zahlungslauf-Planung - Status prüfen
- ⚠️ SEPA-XML-Export - Status prüfen
- ⚠️ Skonto-Optimierung - Status prüfen

---

### MONATLICHE WORKFLOWS (Priorität: MITTEL für Pilot)

#### Workflow 8: USt-Voranmeldung vorbereiten (bis 10. des Folgemonats)
**Wer:** Prokurist + Steuerberaterin
**Heute:** Alle Belege sammeln → Sortieren → Zu Steuerberaterin → Sie macht den Rest
**Pain Points:**
- Belege fehlen → Suche
- Steuerberaterin wartet → Zeitdruck
- Doppelte Arbeit (wir sortieren, sie tippt ab)

**Ablage-System muss können:**
```
[DATEV-Export] → [Zeitraum: November 2024] → [Prüfen] → [Exportieren] → [An Steuerberaterin]
```

**Benötigte Module:**
- ✅ DATEV-Export (5 Routes)
- ⚠️ Monatliche Zusammenfassung - Status prüfen
- ⚠️ Fehlende Belege-Warnung - Status prüfen

**Erfolgskriterium Pilot:**
- [ ] Ein-Klick DATEV-Export funktioniert
- [ ] Export ist vollständig (alle Belege des Monats)
- [ ] Steuerberaterin kann Import bestätigen

---

#### Workflow 9: Zusammenfassende Meldung (ZM) bei EU-Geschäften
**Wer:** Steuerberaterin (mit unseren Daten)
**Heute:** Wir liefern Rechnungsliste → Sie meldet
**Pain Points:**
- Innergemeinschaftliche Lieferungen identifizieren
- Streckengeschäft erkennen (§25b UStG)

**Ablage-System muss können:**
```
[EU-Geschäfte] → [Automatisch erkannt] → [ZM-Daten exportieren]
```

**Benötigte Module:**
- ✅ Streckengeschäft-Erkennung (4 Routes)
- ⚠️ EU-Kunden-Erkennung (USt-IdNr.) - Status prüfen
- ⚠️ ZM-Export - Status prüfen

---

### AD-HOC WORKFLOWS (Priorität: NICE-TO-HAVE für Pilot)

#### Workflow 10: Kundenanfrage beantworten
"Können Sie mir die Rechnung vom März nochmal schicken?"

**Ablage-System muss können:**
```
[Suche: Kunde X, März] → [Rechnung gefunden] → [Per Mail senden] → [Fertig]
```

---

#### Workflow 11: Lieferantenreklamation dokumentieren
"Die Lieferung war beschädigt, wir reklamieren."

**Ablage-System muss können:**
```
[Vorgang anlegen] → [Fotos hinzufügen] → [Mit Lieferschein verknüpfen] → [Status: Offen]
```

---

#### Workflow 12: Betriebsprüfung vorbereiten
Finanzamt will alle Belege 2022 sehen.

**Ablage-System muss können:**
```
[Archiv 2022] → [Alle Belege] → [GoBD-konform] → [Export oder Prüfer-Zugang]
```

---

## Teil 2: Module-zu-Workflow-Mapping

### Vorhandene Module (aus CLAUDE.md / Code-Analyse)

| Modul | Routes | Workflows | Pilot-Kritisch? |
|-------|--------|-----------|-----------------|
| OCR (Multi-Backend) | ~15 Services | WF1 | ✅ JA |
| Dokumentenklassifikation | Teil von OCR | WF1, WF2 | ✅ JA |
| Mahnwesen | 7 Routes | WF3 | ✅ JA |
| Banking/FinTS | 7 Routes | WF4 | ✅ JA |
| Kassenbuch | 2+ Routes | WF5 | ✅ JA |
| DATEV-Export | 5 Routes | WF8 | ✅ JA |
| Streckengeschäft | 4 Routes | WF9 | ⚠️ Später |
| Private DMS | 7 Routes | - | ❌ AUSBLENDEN |
| RAG/LLM | Geplant | WF2 (enhanced) | ❌ Version 2.0 |

---

## Teil 3: Pilot-Blocker (MUSS vor Start gefixt sein)

### 🔴 KRITISCH (Pilot unmöglich ohne diese)

1. **2FA-Frontend-Flow fehlt komplett**
   - Backend existiert, Frontend nicht
   - User wird nach Aktivierung ausgesperrt
   - Geschätzter Aufwand: 3 Tage

2. **Passwort-Reset-UI fehlt**
   - Azubi vergisst Passwort = Showstopper
   - Geschätzter Aufwand: 1 Tag

3. **Keine Empty States**
   - Neuer User sieht leere Seiten
   - "Was soll ich tun?" - Verwirrung
   - Geschätzter Aufwand: 4 Stunden

4. **Kein Onboarding-Flow**
   - Erste Schritte fehlen komplett
   - Geschätzter Aufwand: 2 Tage

### 🟡 WICHTIG (Sollte vor Pilot gefixt sein)

5. **Role-Mapping gebrochen**
   - Wer darf was? Unklar
   - Prokurist braucht mehr Rechte als Azubi

6. **Keine Error-Pages**
   - 404/500 zeigen technische Fehler
   - Verwirrung bei nicht-technischen Usern

7. **Frontend-Tests: Nur 3 vorhanden**
   - Kritische Flows nicht getestet
   - Risiko für Pilot

### 🟢 NICE-TO-HAVE (Nach Pilot)

8. Dashboard-Widgets anpassen
9. Benachrichtigungen (E-Mail bei überfällig)
10. Mobile-Optimierung

---

## Teil 4: Das Pilot-Dashboard (Design-Spezifikation)

### Was der Prokurist morgens um 8:00 sehen muss:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Guten Morgen, [Name]                      📅 Montag, 30.12.2024   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  📊 HEUTE WICHTIG                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ ⚠️  3 Rechnungen überfällig         €2.847    [Ansehen →]  │   │
│  │ 💰 5 Zahlungseingänge zuordnen                 [Prüfen →]  │   │
│  │ 📅 Skonto läuft ab: Müller GmbH     morgen!   [Zahlen →]   │   │
│  │ 📤 DATEV-Export November            offen     [Senden →]   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  💶 FINANZEN IM BLICK                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐               │
│  │ Offene Forderungen   │  │ Offene Verbindlichk. │               │
│  │      €12.450         │  │       €8.200         │               │
│  │ davon überfällig:    │  │ Skonto-Potential:    │               │
│  │      €2.847          │  │       €164           │               │
│  └──────────────────────┘  └──────────────────────┘               │
│                                                                     │
│  🔍 SCHNELLZUGRIFF                                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🔎 Dokument suchen...                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  [+ Neuer Beleg]   [📂 Ablage]   [💳 Kasse]   [📊 Berichte]       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Was der Azubi sehen muss (vereinfacht):

```
┌─────────────────────────────────────────────────────────────────────┐
│  Hallo [Name]                              📅 Montag, 30.12.2024   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  📥 DEINE AUFGABEN HEUTE                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 📬 12 neue Belege erfassen                    [Starten →]  │   │
│  │ 💳 Kassenbuch abschließen                     [Öffnen →]   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  🔍 DOKUMENT SUCHEN                                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🔎 Suchen...                                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  [+ Neuer Beleg]   [💳 Kasse]   [❓ Hilfe]                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Teil 5: Onboarding-Flow für Pilot

### Schritt 1: Erster Login (Prokurist)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  👋 Willkommen bei Ablage-System!                                  │
│                                                                     │
│  In 5 Minuten ist Ihr Büro startklar.                             │
│                                                                     │
│  Schritt 1 von 4: Firma einrichten                                 │
│  ━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░░                                  │
│                                                                     │
│  Firmenname: [________________________]                            │
│  Steuernummer: [________________________]                          │
│  USt-IdNr.: [________________________]                             │
│                                                                     │
│  [ ] Wir haben Bargeschäfte (Kassenbuch aktivieren)               │
│  [ ] Wir haben EU-Kunden (Streckengeschäft aktivieren)            │
│                                                                     │
│                                          [Weiter →]                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Schritt 2: Ersten Beleg scannen

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  📄 Ihr erster Beleg                                               │
│                                                                     │
│  Schritt 2 von 4: Scannen testen                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░                                  │
│                                                                     │
│  Nehmen Sie eine beliebige Rechnung und:                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │         📷 Foto machen                                      │   │
│  │              oder                                           │   │
│  │         📁 Datei hochladen                                  │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  [← Zurück]                              [Überspringen] [Weiter →] │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Schritt 3: Ergebnis zeigen

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ✅ Erkannt!                                                       │
│                                                                     │
│  Schritt 3 von 4: Prüfen und bestätigen                           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░                            │
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ [Vorschau PDF]      │  │ Lieferant: Müller GmbH             │  │
│  │                     │  │ Rechnungs-Nr.: 2024-1234           │  │
│  │                     │  │ Datum: 15.12.2024                  │  │
│  │                     │  │ Betrag: €847,32 (netto €712,03)    │  │
│  │                     │  │ USt: 19%                           │  │
│  │                     │  │ Fällig: 15.01.2025                 │  │
│  │                     │  │ Skonto: 2% bis 25.12.2024          │  │
│  │                     │  │                                    │  │
│  │                     │  │ Buchungsvorschlag:                 │  │
│  │                     │  │ Soll 3400 / Haben 1200             │  │
│  └─────────────────────┘  └─────────────────────────────────────┘  │
│                                                                     │
│  [← Zurück]    [✏️ Korrigieren]                   [✅ Bestätigen]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Schritt 4: Fertig

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  🎉 Geschafft!                                                     │
│                                                                     │
│  Schritt 4 von 4: Los geht's                                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                         │
│                                                                     │
│  Ihr Ablage-System ist eingerichtet.                              │
│                                                                     │
│  📌 Tipp: Beginnen Sie mit dem Poststapel von heute.              │
│  Pro Beleg brauchen Sie jetzt nur noch ~2 Minuten.                │
│                                                                     │
│  Bei Fragen: Ben ist erreichbar unter [Telefon/Chat]              │
│                                                                     │
│                                          [Zum Dashboard →]         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Teil 6: Erfolgsmessung nach Pilot-Woche

### Quantitative Metriken

| Metrik | Vorher (geschätzt) | Ziel Pilot | Gemessen |
|--------|-------------------|------------|----------|
| Zeit pro Eingangsrechnung | 10 Min | <2 Min | [ ] |
| Dokument-Suchzeit | 5+ Min | <30 Sek | [ ] |
| Verpasste Skonto-Fristen/Monat | ~3 | 0 | [ ] |
| Belege nicht gefunden/Woche | ~5 | 0 | [ ] |
| Zeit für DATEV-Export | 2 Std | <15 Min | [ ] |

### Qualitative Fragen nach Pilot-Woche

1. "Findest du Belege jetzt schneller?" (Ja/Nein/Gleich)
2. "War die Bedienung verständlich?" (1-5)
3. "Würdest du zum alten System zurück wollen?" (Ja/Nein)
4. "Was hat gefehlt / genervt?"

---

## Teil 7: Technische Checkliste für Pilot-Start

### Vor Pilot (Ben):

- [ ] 2FA-Frontend implementieren
- [ ] Passwort-Reset-UI implementieren
- [ ] Empty States für alle Listen
- [ ] Onboarding-Flow implementieren
- [ ] Dashboard-Widgets konfigurieren
- [ ] Rollen anlegen (Prokurist, Azubi)
- [ ] Test-Firma anlegen
- [ ] 10 Test-Belege durchspielen

### Am Pilot-Tag 1:

- [ ] System auf Firmen-PC installiert
- [ ] Accounts für alle 4 User angelegt
- [ ] Scanner/Handy-App eingerichtet
- [ ] Erster echter Beleg gemeinsam erfasst
- [ ] Notfall-Kontakt (Ben) kommuniziert

### Tägliche Check-ins während Pilot:

- [ ] Tag 1: "Läuft alles? Erste Fragen?"
- [ ] Tag 3: "Wie viele Belege erfasst? Probleme?"
- [ ] Tag 5: "Habt ihr den DATEV-Export getestet?"
- [ ] Tag 7: Abschluss-Gespräch + Metriken erheben

---

## Teil 8: Ausgeblendete Features für Pilot

Diese Module existieren, sollten aber für den Pilot **versteckt** werden, um Verwirrung zu vermeiden:

1. **Private DMS** (Fahrzeuge, Immobilien) - Anderer Kontext
2. **RAG/LLM Chat** - Version 2.0
3. **Streckengeschäft-Erkennung** - Nur wenn EU-Kunden relevant
4. **Multi-OCR-Backend-Auswahl** - Automatisch im Hintergrund
5. **Admin-Funktionen** (außer für Ben)
6. **API-Dokumentation**
7. **Prometheus/Grafana Metriken**

---

## Teil 9: Risiken und Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| OCR erkennt deutschen Text schlecht | Mittel | Hoch | Vor Pilot mit 50 echten Belegen testen |
| User vergessen Passwort | Hoch | Mittel | Passwort-Reset MUSS funktionieren |
| Scanner/Handy-App funktioniert nicht | Mittel | Hoch | Backup: Datei-Upload im Browser |
| "Zu kompliziert" | Mittel | Hoch | Onboarding + vereinfachte Azubi-Ansicht |
| Performance-Probleme | Niedrig | Mittel | Vorab Lasttest mit 100 Belegen |
| Datenverlust | Niedrig | Kritisch | Tägliches Backup, vor Pilot testen |

---

## Nächste Schritte

1. **Diese Woche:** Blocker 1-4 fixen (2FA, Passwort-Reset, Empty States, Onboarding)
2. **Nächste Woche:** Dashboard anpassen, Rollen konfigurieren
3. **Woche 3:** Interner Test mit 50 Belegen
4. **Woche 4:** Pilot-Start mit Familienbetrieb

---

*Dokument erstellt: 30.12.2024*
*Für: Ablage-System Pilot mit Familienhandelsbetrieb*
*Autor: Ben + Claude*
