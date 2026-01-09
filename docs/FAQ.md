# Häufig gestellte Fragen (FAQ)

> **Ablage-System - Umfassende FAQ für Benutzer, Administratoren und Entwickler**
> Version: 1.0 | Stand: Januar 2025

---

## Inhaltsverzeichnis

1. [Allgemeine Fragen](#allgemeine-fragen)
2. [Erste Schritte](#erste-schritte)
3. [Dokumentenverarbeitung](#dokumentenverarbeitung)
4. [OCR & Texterkennung](#ocr--texterkennung)
5. [Suche & Navigation](#suche--navigation)
6. [Benutzeroberfläche](#benutzeroberfläche)
7. [Sicherheit & Datenschutz](#sicherheit--datenschutz)
8. [Administration](#administration)
9. [Technische Fragen](#technische-fragen)
10. [Fehlerbehebung](#fehlerbehebung)
11. [Integration & API](#integration--api)
12. [Performance & Skalierung](#performance--skalierung)
13. [Backup & Wiederherstellung](#backup--wiederherstellung)
14. [Entwicklung & Erweiterung](#entwicklung--erweiterung)

---

## Allgemeine Fragen

### Was ist das Ablage-System?

Das Ablage-System ist eine Enterprise-Plattform für intelligente Dokumentenverarbeitung. Es digitalisiert, klassifiziert und macht Dokumente durchsuchbar - mit besonderem Fokus auf deutsche Dokumente und höchste Datenschutzstandards.

**Kernfunktionen:**
- GPU-beschleunigte OCR-Texterkennung
- Automatische Dokumentenklassifizierung
- Volltext- und semantische Suche
- DSGVO-konforme Datenhaltung
- 4 Anzeigemodi für optimale Lesbarkeit

### Warum sollte ich das Ablage-System nutzen?

| Vorteil | Beschreibung |
|---------|--------------|
| **On-Premises** | Ihre Daten verlassen niemals Ihre Infrastruktur |
| **Deutsche Optimierung** | Beste Erkennung von Umlauten, Fraktur, ß |
| **GPU-Beschleunigung** | 5-10x schneller als CPU-basierte Lösungen |
| **Enterprise-Ready** | Mandantenfähig, RBAC, Audit-Logs |
| **Open Architecture** | REST-API, Webhooks, SDK für Python & JavaScript |

### Welche Dokumenttypen werden unterstützt?

**Unterstützte Formate:**
- PDF (auch gescannte Dokumente)
- Bilder: PNG, JPEG, TIFF, BMP, WebP
- Office: (Konvertierung zu PDF erforderlich)

**Dokumentkategorien:**
- Rechnungen (Invoices)
- Verträge (Contracts)
- Bestellungen (Orders)
- Lieferscheine (Delivery Notes)
- Korrespondenz (Letters)
- Technische Dokumentation
- Frei definierbare Kategorien

### Wie unterscheidet sich das Ablage-System von anderen DMS?

| Merkmal | Ablage-System | Cloud-DMS | Traditionelles DMS |
|---------|---------------|-----------|-------------------|
| Datenhaltung | On-Premises | Cloud | On-Premises |
| OCR-Qualität | Sehr hoch (GPU) | Mittel | Niedrig |
| Deutsche Texte | Optimiert | Standard | Standard |
| Kosten | Einmalig + Wartung | Monatlich pro User | Hohe Lizenzkosten |
| Anpassbarkeit | Vollständig | Begrenzt | Begrenzt |
| API | Modern (REST) | Variiert | Oft proprietär |

---

## Erste Schritte

### Wie melde ich mich an?

1. Öffnen Sie `https://ablage.ihre-firma.de` im Browser
2. Geben Sie Ihre E-Mail-Adresse ein
3. Geben Sie Ihr Passwort ein
4. Optional: 2-Faktor-Authentifizierung bestätigen
5. Klicken Sie auf **"Anmelden"**

### Ich habe mein Passwort vergessen. Was tun?

1. Klicken Sie auf **"Passwort vergessen?"** auf der Anmeldeseite
2. Geben Sie Ihre E-Mail-Adresse ein
3. Sie erhalten einen Link zum Zurücksetzen (gültig 24 Stunden)
4. Folgen Sie dem Link und setzen Sie ein neues Passwort

**Passwortanforderungen:**
- Mindestens 12 Zeichen
- Groß- und Kleinbuchstaben
- Mindestens eine Zahl
- Mindestens ein Sonderzeichen

### Wie lade ich mein erstes Dokument hoch?

**Per Drag & Drop:**
1. Ziehen Sie die Datei in den Browser
2. Lassen Sie sie im Upload-Bereich fallen
3. Warten Sie auf die Verarbeitung

**Per Button:**
1. Klicken Sie auf **"+ Dokument hochladen"**
2. Wählen Sie die Datei(en) aus
3. Optional: Wählen Sie den Dokumenttyp
4. Klicken Sie auf **"Hochladen"**

### Wie lange dauert die Verarbeitung?

| Dokumentgröße | GPU (RTX 4080) | CPU-Fallback |
|---------------|----------------|--------------|
| 1 Seite | 0.5-1 Sekunde | 5-10 Sekunden |
| 10 Seiten | 5-10 Sekunden | 1-2 Minuten |
| 100 Seiten | 1-2 Minuten | 10-20 Minuten |

### Kann ich mehrere Dokumente gleichzeitig hochladen?

Ja, Batch-Uploads werden unterstützt:
- Wählen Sie mehrere Dateien (Strg+Klick oder Shift+Klick)
- Oder ziehen Sie einen ganzen Ordner in den Browser
- Maximum: 100 Dateien oder 500 MB pro Upload

---

## Dokumentenverarbeitung

### Was passiert nach dem Upload?

```
Upload → Validierung → OCR-Verarbeitung → Klassifizierung → Indexierung → Fertig
```

1. **Validierung**: Dateiformat und Größe werden geprüft
2. **OCR-Verarbeitung**: Text wird aus dem Dokument extrahiert
3. **Klassifizierung**: Dokumenttyp wird automatisch erkannt
4. **Indexierung**: Dokument wird für die Suche vorbereitet
5. **Fertig**: Dokument ist durchsuchbar und verfügbar

### Wie funktioniert die automatische Klassifizierung?

Das System analysiert:
- Erkannten Text (Schlüsselwörter wie "Rechnung", "Vertrag")
- Layout und Struktur
- Absender/Empfänger-Informationen
- Datumsformate und Beträge

Sie können die automatische Klassifizierung jederzeit manuell korrigieren.

### Kann ich die Klassifizierung ändern?

Ja:
1. Öffnen Sie das Dokument
2. Klicken Sie auf **"Bearbeiten"** (Stift-Symbol)
3. Ändern Sie den Dokumenttyp im Dropdown
4. Klicken Sie auf **"Speichern"**

Ihre Korrektur verbessert die zukünftige automatische Erkennung.

### Werden meine Original-Dokumente verändert?

**Nein.** Die Originaldateien werden unverändert gespeichert. Das System erstellt:
- Eine Kopie für die OCR-Verarbeitung
- Extrahierten Text als Metadaten
- Vorschaubilder für die Anzeige

### Wie kann ich Dokumente taggen?

1. Öffnen Sie das Dokument
2. Klicken Sie auf **"Tags bearbeiten"**
3. Fügen Sie Tags hinzu (Komma-getrennt)
4. Oder wählen Sie aus vorhandenen Tags
5. **"Speichern"**

**Tag-Best-Practices:**
- Verwenden Sie konsistente Begriffe
- Nutzen Sie Hierarchien: `projekt:alpha`, `kunde:mustermann`
- Begrenzen Sie sich auf 5-10 Tags pro Dokument

### Kann ich Dokumente mit anderen teilen?

Ja, über die Freigabe-Funktion:
1. Rechtsklick auf Dokument → **"Freigeben"**
2. Wählen Sie Benutzer oder Gruppen
3. Legen Sie Berechtigungen fest:
   - **Lesen**: Nur Ansicht
   - **Bearbeiten**: Metadaten ändern
   - **Verwalten**: Freigabe ändern, löschen
4. **"Freigabe erstellen"**

---

## OCR & Texterkennung

### Welche OCR-Backends werden verwendet?

Das System nutzt drei spezialisierte OCR-Engines:

| Backend | Stärken | VRAM |
|---------|---------|------|
| **DeepSeek-Janus-Pro** | Beste Umlaut-Erkennung, Fraktur, komplexe Layouts | 12 GB |
| **GOT-OCR 2.0** | Tabellen, mathematische Formeln, schnell | 10 GB |
| **Surya + Docling** | CPU-Fallback, Layout-Analyse | 0 GB |

Das System wählt automatisch das beste Backend basierend auf dem Dokumenttyp.

### Wie gut ist die Erkennung deutscher Texte?

**Sehr gut.** Das System ist für deutsche Dokumente optimiert:
- Umlaute (ä, ö, ü): 99%+ Genauigkeit
- Eszett (ß): Korrekte Unterscheidung von ss
- Frakturschrift: Unterstützt
- Schweizer/Österreichische Varianten: Unterstützt

### Mein Dokument wurde nicht richtig erkannt. Was tun?

1. **Bildqualität prüfen**: Mindestens 300 DPI empfohlen
2. **Andere Engine versuchen**:
   - Dokument öffnen → **"Erneut verarbeiten"**
   - Backend manuell auswählen
3. **Manuell korrigieren**:
   - Text bearbeiten und speichern
   - Das System lernt aus Korrekturen

### Kann ich den erkannten Text bearbeiten?

Ja:
1. Öffnen Sie das Dokument
2. Wechseln Sie zum Tab **"Text"**
3. Klicken Sie auf **"Bearbeiten"**
4. Korrigieren Sie den Text
5. **"Speichern"**

### Werden handschriftliche Texte erkannt?

**Eingeschränkt.** Handschrift wird mit geringerer Genauigkeit erkannt:
- Druckschrift: ~70-80% Genauigkeit
- Kursive Schrift: ~50-60% Genauigkeit
- Für handschriftliche Dokumente empfehlen wir manuelle Nachbearbeitung

### Wie kann ich die OCR-Qualität verbessern?

**Vor dem Scannen:**
- 300 DPI oder höher verwenden
- Gerade ausrichten
- Guten Kontrast sicherstellen
- Knicke und Flecken vermeiden

**Nach dem Upload:**
- Vorverarbeitung aktivieren (automatische Entzerrung)
- Spezialisiertes Backend wählen
- Bei Bedarf manuell korrigieren

---

## Suche & Navigation

### Wie suche ich nach Dokumenten?

**Schnellsuche:**
- Drücken Sie `Ctrl+K` oder klicken Sie auf die Suchleiste
- Geben Sie Suchbegriffe ein
- Ergebnisse erscheinen sofort

**Erweiterte Suche:**
- Klicken Sie auf **"Erweiterte Suche"**
- Filtern Sie nach:
  - Dokumenttyp
  - Datumsbereich
  - Tags
  - Ersteller
  - Status

### Welche Suchoperatoren werden unterstützt?

| Operator | Beispiel | Beschreibung |
|----------|----------|--------------|
| `""` | `"exakte phrase"` | Exakte Phrasensuche |
| `AND` | `rechnung AND 2024` | Beide Begriffe müssen vorkommen |
| `OR` | `invoice OR rechnung` | Einer der Begriffe |
| `NOT` | `vertrag NOT entwurf` | Begriff ausschließen |
| `*` | `rech*` | Wildcard (findet rechnung, rechnungen, etc.) |
| `type:` | `type:invoice` | Nach Dokumenttyp filtern |
| `date:` | `date:2024-01` | Nach Datum filtern |
| `tag:` | `tag:wichtig` | Nach Tag filtern |

### Kann ich nach Inhalten in Tabellen suchen?

Ja, Tabelleninhalte werden vollständig indexiert. Suchen Sie einfach nach:
- Zellenwerten: `1.234,56 EUR`
- Spaltenüberschriften: `Artikelnummer`
- Kombinationen: `Artikelnummer 12345`

### Wie speichere ich häufige Suchen?

1. Führen Sie die Suche aus
2. Klicken Sie auf **"Suche speichern"**
3. Geben Sie einen Namen ein
4. Optional: Als Standard festlegen

Gespeicherte Suchen finden Sie unter **"Meine Suchen"**.

### Gibt es eine semantische Suche?

**Ja.** Das System versteht Bedeutung, nicht nur Schlüsselwörter:
- Suche nach "Zahlungsaufforderung" findet auch "Rechnung", "Mahnung"
- Suche nach "KFZ" findet auch "Auto", "Fahrzeug", "PKW"

Die semantische Suche nutzt Vektor-Embeddings (Qdrant) für beste Ergebnisse.

---

## Benutzeroberfläche

### Welche Anzeigemodi gibt es?

| Modus | Beschreibung | Verwendung |
|-------|--------------|------------|
| **Dark Mode** | Dunkler Hintergrund | Standard, Abends |
| **Light Mode** | Heller Hintergrund | Tagsüber, helle Umgebung |
| **Whitescreen** | Hoher Kontrast (weiß) | Sehbeeinträchtigungen |
| **Blackscreen** | Hoher Kontrast (schwarz) | OLED-Displays, Dunkelheit |

Wechseln Sie den Modus über das Symbol oben rechts oder `Ctrl+Shift+D`.

### Kann ich das Layout anpassen?

Ja:
- **Listenansicht** vs. **Kachelansicht**: Umschalten oben rechts
- **Seitenleiste**: Ein-/ausblenden mit `Ctrl+B`
- **Spalten**: Anpassen per Drag & Drop
- **Sortierung**: Klick auf Spaltenüberschrift

### Welche Tastenkürzel gibt es?

| Tastenkombination | Aktion |
|-------------------|--------|
| `Ctrl+K` | Suche öffnen |
| `Ctrl+U` | Dokument hochladen |
| `Ctrl+N` | Neuer Ordner |
| `Ctrl+B` | Seitenleiste ein/aus |
| `Ctrl+Shift+D` | Anzeigemodus wechseln |
| `Enter` | Dokument öffnen |
| `Delete` | Dokument löschen |
| `Ctrl+D` | Dokument herunterladen |
| `F2` | Umbenennen |
| `Escape` | Dialog schließen |

### Funktioniert das System auf Mobilgeräten?

**Ja.** Die Benutzeroberfläche ist responsiv:
- Smartphones: Optimierte Touch-Steuerung
- Tablets: Volle Funktionalität
- Empfehlung: Neuere Browser (Chrome, Firefox, Safari, Edge)

### Kann ich die Sprache ändern?

Aktuell wird **Deutsch** als Primärsprache unterstützt. Englische Lokalisierung ist in Planung. System-Logs und API-Dokumentation sind auf Englisch.

---

## Sicherheit & Datenschutz

### Wie werden meine Daten geschützt?

**Technische Maßnahmen:**
- Verschlüsselung bei Übertragung (TLS 1.3)
- Verschlüsselung bei Speicherung (AES-256)
- Rollenbasierte Zugriffskontrolle (RBAC)
- Audit-Logging aller Zugriffe
- Automatische Session-Timeouts

**Organisatorische Maßnahmen:**
- Regelmäßige Sicherheitsaudits
- Penetrationstests
- Schulungen für Administratoren

### Ist das System DSGVO-konform?

**Ja.** Vollständige DSGVO-Konformität:
- Keine Datenübertragung an Dritte
- Recht auf Auskunft (Art. 15)
- Recht auf Berichtigung (Art. 16)
- Recht auf Löschung (Art. 17)
- Recht auf Datenübertragbarkeit (Art. 20)
- Detaillierte Datenschutzerklärung

Siehe auch: `.claude/Docs/Compliance/GDPR-User-Guide.md`

### Wer hat Zugriff auf meine Dokumente?

- **Sie** haben vollen Zugriff auf Ihre Dokumente
- **Von Ihnen freigegebene** Personen (mit den von Ihnen definierten Rechten)
- **Administratoren** können Berechtigungen verwalten, aber nicht automatisch auf Inhalte zugreifen
- **Niemand** sonst

### Werden meine Dokumente in die Cloud übertragen?

**Nein.** Das Ablage-System ist eine On-Premises-Lösung:
- Alle Daten bleiben auf Ihren Servern
- Keine Verbindung zu Cloud-Diensten
- Keine externen OCR-APIs
- Vollständige Datensouveränität

### Wie kann ich meine Daten exportieren?

1. **Einstellungen** → **Datenschutz** → **Daten exportieren**
2. Wählen Sie das Format:
   - JSON (maschinenlesbar)
   - CSV (Tabellenkalkulation)
   - ZIP (inkl. Originaldateien)
3. Wählen Sie den Umfang
4. **"Export starten"**

### Wie kann ich mein Konto löschen?

1. **Einstellungen** → **Datenschutz** → **Konto löschen**
2. Wählen Sie, was gelöscht werden soll
3. Geben Sie Ihr Passwort zur Bestätigung ein
4. **"Konto unwiderruflich löschen"**

**Bearbeitungszeit:** Sofort (Deaktivierung), 30 Tage (endgültige Löschung)

---

## Administration

### Wie erstelle ich neue Benutzer?

1. **Admin** → **Benutzerverwaltung** → **"+ Benutzer erstellen"**
2. Füllen Sie die Felder aus:
   - E-Mail (Pflicht)
   - Name
   - Rolle
   - Abteilung
3. **"Erstellen"**

Der Benutzer erhält eine E-Mail mit Aktivierungslink.

### Welche Rollen gibt es?

| Rolle | Rechte |
|-------|--------|
| **Benutzer** | Dokumente hochladen, eigene verwalten |
| **Power-User** | + Batch-Operationen, erweiterte Suche |
| **Editor** | + Dokumente anderer bearbeiten |
| **Reviewer** | + Dokumente freigeben, Qualitätskontrolle |
| **Admin** | Vollzugriff auf Systemverwaltung |
| **System-Admin** | + Infrastruktur, Backup, Sicherheit |

### Wie setze ich ein Benutzerpasswort zurück?

1. **Admin** → **Benutzerverwaltung**
2. Suchen Sie den Benutzer
3. **Aktionen** → **"Passwort zurücksetzen"**
4. Der Benutzer erhält einen Reset-Link per E-Mail

### Wie konfiguriere ich LDAP/Active Directory?

1. **Admin** → **Einstellungen** → **Authentifizierung**
2. Wählen Sie **"LDAP/AD"**
3. Konfigurieren Sie:
   ```
   Server: ldaps://ad.firma.de:636
   Base DN: dc=firma,dc=de
   Bind DN: cn=service,ou=users,dc=firma,dc=de
   Filter: (objectClass=user)
   ```
4. **"Verbindung testen"** → **"Speichern"**

### Wie überwache ich die Systemauslastung?

**Grafana-Dashboard:**
- URL: `https://ablage.ihre-firma.de:3002`
- Login: Admin-Credentials
- Dashboards:
  - System Overview
  - OCR Processing
  - GPU Status
  - API Metrics

### Wie konfiguriere ich E-Mail-Benachrichtigungen?

**Admin** → **Einstellungen** → **E-Mail**:
```
SMTP-Server: smtp.firma.de
Port: 587
Verschlüsselung: STARTTLS
Benutzer: ablage@firma.de
Absender: Ablage-System <ablage@firma.de>
```

---

## Technische Fragen

### Welche Systemanforderungen gibt es?

**Server (Minimum):**
| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| CPU | 8 Cores | 16+ Cores |
| RAM | 32 GB | 64+ GB |
| GPU | RTX 3080 (10 GB) | RTX 4080 (16 GB) |
| Speicher | 500 GB SSD | 2+ TB NVMe |
| OS | Ubuntu 22.04 | Ubuntu 22.04 |

**Client:**
- Moderner Browser (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- JavaScript aktiviert
- Bildschirmauflösung: 1280x720+

### Welche Ports werden verwendet?

| Port | Dienst | Protokoll |
|------|--------|-----------|
| 80 | HTTP (Redirect) | TCP |
| 443 | HTTPS (Frontend) | TCP |
| 8000 | API (intern) | TCP |
| 5433 | PostgreSQL | TCP |
| 6380 | Redis | TCP |
| 9000 | MinIO API | TCP |
| 9001 | MinIO Console | TCP |
| 3002 | Grafana | TCP |
| 9090 | Prometheus | TCP |

### Wie aktualisiere ich das System?

```bash
# 1. Backup erstellen
docker-compose exec backend python -m app.cli backup create

# 2. Neue Version herunterladen
git pull origin main

# 3. Container neu bauen
docker-compose build

# 4. Migrationen ausführen
docker-compose exec backend alembic upgrade head

# 5. System neu starten
docker-compose up -d

# 6. Health-Check
curl https://localhost/api/v1/health
```

### Wie skaliere ich das System?

**Horizontal (mehr Worker):**
```bash
docker-compose up -d --scale worker=4
```

**Vertikal (mehr Ressourcen):**
- GPU upgraden (RTX 4090, A100)
- RAM erhöhen
- SSD-RAID konfigurieren

Siehe: `.claude/Docs/Guides/Scalability-Guide.md`

### Welche Datenbank wird verwendet?

**PostgreSQL 16** mit Erweiterungen:
- `pgvector`: Für semantische Suche
- `pg_trgm`: Für Fuzzy-Suche
- `uuid-ossp`: Für UUIDs

---

## Fehlerbehebung

### Das Dokument wird nicht verarbeitet. Was tun?

1. **Status prüfen**: Dokument öffnen → Status-Badge
2. **Logs prüfen**: Admin → System → Logs
3. **Häufige Ursachen:**
   - GPU nicht verfügbar → CPU-Fallback aktivieren
   - Datei beschädigt → Andere Datei testen
   - Queue voll → Warten oder Priorität erhöhen

### Die Suche findet nichts. Warum?

1. **Indexierung abwarten**: Neue Dokumente brauchen ~1 Minute
2. **Suchbegriff prüfen**: Tippfehler? Zu spezifisch?
3. **Filter zurücksetzen**: Klicken Sie auf "Filter löschen"
4. **Volltext-Suche**: In Anführungszeichen setzen

### Das System ist langsam. Was kann ich tun?

**Als Benutzer:**
- Browser-Cache leeren
- Weniger Dokumente pro Seite anzeigen
- Andere Tageszeit wählen

**Als Admin:**
- GPU-Auslastung prüfen (`nvidia-smi`)
- Redis-Cache leeren
- Worker neu starten
- Logs auf Fehler prüfen

### Ich sehe "GPU Out of Memory". Was bedeutet das?

Die GPU hat nicht genug Speicher für die aktuelle Operation. Das System wechselt automatisch zum CPU-Fallback.

**Lösungen:**
- Warten bis andere Verarbeitungen abgeschlossen sind
- Kleinere Dokumente einzeln verarbeiten
- GPU-Batch-Größe reduzieren (Admin-Einstellung)

### Wie melde ich einen Fehler?

1. Notieren Sie:
   - Was Sie getan haben
   - Was passiert ist
   - Was Sie erwartet haben
   - Zeitpunkt des Fehlers
   - Fehlermeldung (Screenshot)
2. Kontaktieren Sie den Administrator
3. Oder öffnen Sie ein Ticket im internen System

---

## Integration & API

### Gibt es eine API?

**Ja.** Vollständige REST-API:
- OpenAPI 3.1 Dokumentation: `/api/docs`
- Swagger UI: `/api/docs/swagger`
- ReDoc: `/api/docs/redoc`

### Wie authentifiziere ich mich an der API?

**Option 1: JWT-Token**
```bash
# Login
curl -X POST https://ablage.firma.de/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@firma.de", "password": "***"}'

# API-Aufruf
curl https://ablage.firma.de/api/v1/documents \
  -H "Authorization: Bearer eyJ..."
```

**Option 2: API-Key**
```bash
curl https://ablage.firma.de/api/v1/documents \
  -H "X-API-Key: ak_live_..."
```

### Gibt es SDKs?

**Python:**
```python
from ablage_client import AblageClient

client = AblageClient("https://ablage.firma.de", api_key="...")
docs = client.documents.list()
```

**JavaScript/TypeScript:**
```typescript
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({ apiKey: '...' });
const docs = await client.documents.list();
```

Siehe: `.claude/Docs/API/SDK-Examples.md`

### Kann ich Webhooks nutzen?

**Ja.** Unterstützte Events:
- `document.created`
- `document.processed`
- `document.deleted`
- `ocr.completed`
- `ocr.failed`

Konfiguration: Admin → Einstellungen → Webhooks

### Kann ich das System in SAP integrieren?

**Ja.** Über die REST-API oder spezielle SAP-Konnektoren:
- SAP Business One: Direkte Integration
- SAP S/4HANA: Über RFC-Adapter
- DATEV-Export: Native Unterstützung

Siehe: `.claude/Docs/API/Integration-Guide.md`

---

## Performance & Skalierung

### Wie viele Dokumente kann das System verarbeiten?

| Hardware | Dokumente/Stunde | Dokumente/Tag |
|----------|------------------|---------------|
| RTX 3080 | ~300 | ~7.000 |
| RTX 4080 | ~500 | ~12.000 |
| RTX 4090 | ~700 | ~17.000 |
| Multi-GPU (2x4080) | ~1.000 | ~24.000 |

### Wie viele Benutzer werden unterstützt?

Das System skaliert mit der Infrastruktur:
- **Standard**: 50-100 gleichzeitige Benutzer
- **Erweitert**: 500+ gleichzeitige Benutzer
- **Enterprise**: 1.000+ mit Load-Balancing

### Wie optimiere ich die Suchgeschwindigkeit?

1. **Indexierung aktuell halten**: Regelmäßige Reindexierung
2. **Qdrant nutzen**: Vektor-Suche für semantische Abfragen
3. **Redis-Cache**: Häufige Abfragen werden gecacht
4. **Filter reduzieren**: Weniger Filter = schneller

### Warum ist die GPU-Auslastung so hoch?

Die GPU wird für OCR-Verarbeitung genutzt. Hohe Auslastung (70-85%) ist normal und erwünscht. Problematisch wird es erst bei:
- Dauerhaft 100%: Queue-Stau möglich
- OOM-Fehler: Batch-Größe reduzieren
- Thermal Throttling: Kühlung prüfen

---

## Backup & Wiederherstellung

### Wie oft werden Backups erstellt?

**Standard-Zeitplan:**
| Komponente | Intervall | Aufbewahrung |
|------------|-----------|--------------|
| Datenbank (PostgreSQL) | Täglich 02:30 | 30 Tage |
| Dateien (MinIO) | Täglich 03:00 | 90 Tage |
| Konfiguration | Wöchentlich | 90 Tage |
| Komplett-Backup | Sonntag 02:00 | 12 Wochen |

### Wie stelle ich ein Backup wieder her?

```bash
# 1. System stoppen
docker-compose down

# 2. Backup auswählen
ls /backups/

# 3. Wiederherstellung starten
./scripts/restore.sh /backups/backup_2025-01-08.tar.gz

# 4. System starten
docker-compose up -d

# 5. Verifizierung
curl https://localhost/api/v1/health
```

### Wo werden Backups gespeichert?

**Lokal:** `/var/backups/ablage/`
**Remote (optional):** Konfigurierbar (NFS, S3-kompatibel, SFTP)

### Wie teste ich Backup-Wiederherstellung?

Vierteljährliche DR-Tests empfohlen:
1. Erstellen Sie eine Test-Umgebung
2. Spielen Sie das Backup ein
3. Verifizieren Sie Datenintegrität
4. Dokumentieren Sie Ergebnisse

Siehe: `.claude/Docs/Guides/Disaster-Recovery.md`

---

## Entwicklung & Erweiterung

### Kann ich eigene Plugins entwickeln?

Das System ist erweiterbar über:
- **Webhooks**: Für Event-basierte Integration
- **API**: Für eigene Frontends/Workflows
- **Custom OCR**: Eigene Backends einbinden

### Welche Programmiersprachen werden unterstützt?

**Backend:** Python 3.11+
**Frontend:** TypeScript/React
**SDKs:** Python, JavaScript/TypeScript
**API:** Jede Sprache mit HTTP-Client

### Wie richte ich eine Entwicklungsumgebung ein?

```bash
# Repository klonen
git clone https://github.com/firma/ablage-system.git
cd ablage-system

# Docker-Umgebung starten
docker-compose -f docker-compose.dev.yml up -d

# Frontend starten (Development)
cd frontend && npm install && npm run dev

# Tests ausführen
docker-compose exec backend pytest
```

Siehe: `.claude/Docs/Guides/Developer-Onboarding.md`

### Wie kann ich zur Entwicklung beitragen?

1. Fork erstellen
2. Feature-Branch anlegen
3. Änderungen implementieren
4. Tests schreiben
5. Pull Request erstellen

**Code-Standards:**
- Type-Hints (Python)
- TypeScript strict mode
- 80%+ Test-Coverage
- Dokumentation aktualisieren

---

## Kontakt & Support

### An wen wende ich mich bei Problemen?

| Problem | Kontakt |
|---------|---------|
| Technische Fragen | IT-Helpdesk |
| Berechtigungen | Ihr Vorgesetzter |
| Datenschutz | Datenschutzbeauftragter |
| Sicherheitsvorfälle | security@firma.de |
| Feature-Requests | product@firma.de |

### Wo finde ich weitere Dokumentation?

- **Benutzerhandbuch**: `docs/USER_GUIDE.md`
- **Admin-Handbuch**: `docs/ADMIN_GUIDE.md`
- **API-Dokumentation**: `/api/docs`
- **Entwickler-Docs**: `.claude/Docs/`

### Gibt es Schulungen?

Ja, kontaktieren Sie die IT-Abteilung für:
- Einführungsschulung (2 Stunden)
- Power-User-Training (4 Stunden)
- Admin-Schulung (1 Tag)
- Entwickler-Workshop (2 Tage)

---

*Letzte Aktualisierung: Januar 2025*
*Fragen, die hier nicht beantwortet werden? Kontaktieren Sie den IT-Support.*
