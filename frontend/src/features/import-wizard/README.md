# Import Wizard

Multi-step wizard für geführten Import von Dokumenten im Ablage-System.

## Überblick

Der Import-Assistent führt Benutzer durch einen 5-stufigen Prozess:

1. **Quelle wählen** - E-Mail, Ordner oder CSV/Lexware
2. **Konfiguration** - Bestehende Config auswählen oder neue erstellen
3. **Vorschau** - Zu importierende Elemente überprüfen
4. **Regeln** - Import-Regeln aktivieren/deaktivieren
5. **Import starten** - Zusammenfassung und Ausführung

## Dateien

```
frontend/src/features/import-wizard/
├── api/
│   └── wizard-api.ts           # TanStack Query hooks
├── components/
│   └── ImportWizard.tsx        # Haupt-Wizard-Komponente
└── index.ts                    # Exports
```

## Route

```
/admin/import-wizard
```

Datei: `frontend/src/app/routes/admin.import-wizard.tsx`

## API Integration

### Bestehende Endpoints (genutzt)

- `GET /imports/email/configs` - Liste Email-Konfigurationen
- `GET /imports/folder/configs` - Liste Ordner-Konfigurationen
- `GET /imports/rules` - Liste Import-Regeln
- `POST /imports/email/configs/{id}/sync` - Starte Email-Import
- `POST /imports/folder/configs/{id}/poll` - Starte Ordner-Import

### Neue Endpoints (mit Fallback)

- `POST /imports/email/configs/{id}/preview` - Vorschau Email-Import
- `POST /imports/folder/configs/{id}/preview` - Vorschau Ordner-Import

**Hinweis**: Preview-Endpoints werden gracefully mit 404-Fallback behandelt.
Wenn der Endpoint nicht existiert, zeigt der Wizard eine Warnung und Mock-Daten an.

## Features

### Step 1: Quelle wählen
- 3 große Karten für Email/Ordner/CSV
- Icons und Beschreibungen
- Klick zum Auswählen

### Step 2: Konfiguration
- Liste bestehender Configs mit Status-Badges
- Anzeige von Server/Pfad und Dokumenten-Anzahl
- Info-Alert wenn keine Configs vorhanden

### Step 3: Vorschau
- 3 Summary-Cards (Anzahl, Größe, Dauer)
- Warnungen als Alert
- Beispiel-Liste der zu importierenden Elemente
- "Bereit zum Import" Indikator

### Step 4: Regeln
- Toggle für Regel-Anwendung
- Liste der aktiven Regeln mit Priorität
- Match-Count für jede Regel

### Step 5: Import starten
- Zusammenfassung der Auswahl
- Start-Button
- Progress-Anzeige während Import
- Success/Error-Feedback
- Link zu Import-Logs nach Erfolg

## UI-Komponenten

- **shadcn/ui**: Card, Button, Badge, Alert, Progress, Skeleton
- **Lucide Icons**: Mail, Folder, FileSpreadsheet, CheckCircle, etc.
- **UnifiedErrorBoundary**: Fehlerbehandlung

## Styling

- Responsive Grid-Layout (md:grid-cols-3)
- Hover-Effekte auf klickbaren Cards
- Farbcodierte Status-Badges
- Progress-Stepper mit Verbindungslinien
- Dark-Mode kompatibel

## Verwendung

```tsx
import { ImportWizard } from '@/features/import-wizard';

function MyPage() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <ImportWizard />
    </UnifiedErrorBoundary>
  );
}
```

## Erweiterungen

Mögliche zukünftige Verbesserungen:

- **CSV-Upload**: File-Dropzone für CSV-Import in Step 2
- **Regel-Preview**: Test-Funktion für Regeln mit Beispiel-Daten
- **Echtzeit-Progress**: WebSocket-Update während Import
- **Batch-Import**: Mehrere Configs gleichzeitig
- **Scheduling**: Import zu bestimmten Zeiten planen

## CRITICAL: German Language

**Alle Texte sind auf Deutsch!** Keine englischen Texte in der UI.

## CRITICAL: shadcn Select

**NIEMALS `value=""` in Select-Komponenten verwenden!**
Nutze stattdessen `value="all"` oder `value="auto"`.
