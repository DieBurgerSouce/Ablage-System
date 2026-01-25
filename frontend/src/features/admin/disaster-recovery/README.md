# Disaster Recovery Dashboard

Umfassendes Disaster Recovery Management-Frontend für Backup-Monitoring, Restore-Tests und Recovery-Planung.

## Features

### 1. Backup Status Overview
- **System-Health-Monitoring**: Service-Status, Verschlüsselung, Speichernutzung
- **Backup-Zeitplan**: Letzte und nächste geplante Vollsicherung
- **Speicher-Alerts**: Warnung bei >80% Speichernutzung
- **Echtzeit-Status**: Auto-Refresh alle 30 Sekunden

### 2. Automatische Restore-Tests
- **Wöchentliche Tests**: Vollständige Wiederherstellungstests
- **Test-History**: 90-Tage-Übersicht mit Success Rate
- **RTO/RPO-Tracking**: Validierung der Recovery-Ziele
- **Detaillierte Reports**: Schritt-für-Schritt Validierung

### 3. RTO/RPO Monitoring
- **Recovery Time Objective (RTO)**: Ziel vs. Ist-Zeit
- **Recovery Point Objective (RPO)**: Datenverlust-Messung
- **Compliance-Rate**: Prozentsatz der eingehaltenen Ziele
- **Trend-Analyse**: Durchschnittswerte über 90 Tage
- **Automatische Alerts**: Bei Ziel-Verfehlungen

### 4. Backup-Integritäts-Checks
- **Einzelvalidierung**: Validierung spezifischer Backups
- **Bulk-Validierung**: Alle Backups auf einmal prüfen
- **Status-Tracking**: Gültig/Fehlerhaft/Unvalidiert
- **Verschlüsselungs-Check**: Übersicht verschlüsselter Backups
- **Detaillierte Fehler**: Validation errors und warnings

### 5. Recovery Playbook Generator
- **5 Disaster-Typen**:
  - Hardware-Ausfall
  - Datenkorruption
  - Ransomware-Angriff
  - Naturkatastrophe
  - Menschlicher Fehler
- **4 Schweregrade**: Kritisch, Hoch, Mittel, Niedrig
- **Step-by-Step Anleitung**: Vorbereitung → Ausführung → Validierung → Kommunikation
- **Export-Funktion**: Download als Textdatei
- **Notfallkontakte**: Eingebettete Kontaktinformationen
- **CLI-Befehle**: Copy-paste-fähige Kommandos

## Architektur

### Komponenten-Struktur
```
disaster-recovery/
├── api.ts                          # API-Client mit TypeScript-Types
├── hooks.ts                        # TanStack Query Hooks
├── types.ts                        # Shared Types
├── DisasterRecoveryPage.tsx        # Main Dashboard
├── components/
│   ├── BackupStatusCard.tsx        # Status-Übersicht
│   ├── RestoreTestsPanel.tsx       # Test-History
│   ├── BackupValidationPanel.tsx   # Integritätsprüfung
│   ├── RTOMonitoringCard.tsx       # RTO/RPO-Metriken
│   ├── RecoveryPlaybook.tsx        # Playbook-Generator
│   └── index.ts                    # Component Barrel
└── index.ts                        # Feature Barrel
```

### Backend-APIs
Alle Endpunkte unter `/api/v1/backup/`:

**Status & Listen**:
- `GET /status` - Backup-System-Status
- `GET /list` - Alle Backups

**Validierung**:
- `POST /validate` - Einzelnes Backup validieren
- `POST /validate-all` - Alle Backups validieren

**Backup-Operationen**:
- `POST /full` - Vollsicherung erstellen
- `POST /restore/full` - Full Restore (mit dry_run)

**Restore-Tests**:
- `POST /restore/test` - Restore-Test durchführen
- `GET /restore/test-history?days=90` - Test-Historie

**Metriken**:
- `GET /metrics/rto-rpo` - RTO/RPO Metriken

**Playbook**:
- `POST /playbook/generate` - Playbook generieren
- `POST /playbook/export` - PDF-Export

## Verwendung

### Route
```typescript
/admin/disaster-recovery
```

### Hooks
```typescript
import {
  useBackupStatus,
  useBackups,
  useRestoreTestHistory,
  useRTOMetrics,
  useValidateBackup,
  useValidateAllBackups,
  useCreateFullBackup,
  useRunRestoreTest,
  useGeneratePlaybook,
} from '@/features/admin/disaster-recovery';

// Beispiel: Backup-Status abrufen
const { data: status, isLoading } = useBackupStatus();

// Beispiel: Restore-Test starten
const runTestMutation = useRunRestoreTest();
await runTestMutation.mutateAsync({ test_type: 'full', dry_run: false });
```

### Komponenten
```typescript
import {
  BackupStatusCard,
  RestoreTestsPanel,
  BackupValidationPanel,
  RTOMonitoringCard,
  RecoveryPlaybook,
} from '@/features/admin/disaster-recovery';

// Verwendung in eigenem Dashboard
<BackupStatusCard status={status} isLoading={isLoading} />
```

## UI-Patterns

### Tab-basierte Navigation
4 Haupttabs:
1. **Übersicht**: Status + RTO/RPO Monitoring
2. **Restore-Tests**: Test-History und neuen Test starten
3. **Validierung**: Backup-Integritätschecks
4. **Playbook**: Recovery-Anleitung generieren

### Responsive Design
- **Desktop**: 2-Spalten Layout für Status-Cards
- **Tablet**: 1-Spalte mit voller Breite
- **Mobile**: Stack-Layout mit Touch-optimierten Buttons

### Accessibility
- **ARIA-Labels**: Alle interaktiven Elemente
- **Keyboard-Navigation**: Tab-Navigation durch alle Controls
- **Screen-Reader**: Semantisches HTML mit role-Attributen
- **Color-Contrast**: WCAG 2.1 AA konform

### Loading States
- **Skeleton Loaders**: Während Daten laden
- **Spinner**: Bei Mutationen (Backup erstellen, Tests starten)
- **Disabled States**: Buttons während laufender Operationen

### Error Handling
- **Toast-Notifications**: Erfolg/Fehler-Meldungen
- **Alert-Banner**: System-Warnungen (z.B. RTO verfehlt)
- **Inline-Errors**: Validation-Fehler bei einzelnen Backups

## Internationalisierung

Alle UI-Texte auf **Deutsch**:
- Labels und Beschreibungen
- Fehlermeldungen
- Datum/Zeit-Formatierung (de-DE Locale)
- Zahlenformatierung (Komma als Dezimaltrennzeichen)

## Monitoring & Alerts

### Automatische Warnungen
- **Speicher >80%**: Rotes Alert-Banner
- **Service inaktiv**: System-Status Badge rot
- **RTO/RPO verfehlt**: Destructive Badge + Alert
- **Fehlgeschlagene Tests**: Alert im Restore-Panel
- **Keine Tests (90 Tage)**: Warnung in RTO-Card

### Health-Status-Berechnung
```typescript
isSystemHealthy =
  service_aktiv &&
  encryption_aktiv &&
  rto_compliance >= 0.9 &&
  rpo_compliance >= 0.9
```

## Datenformatierung

### Datum/Zeit
```typescript
formatDate('2026-01-24T10:30:00Z') // → "24.01.2026 10:30"
```

### Größen
```typescript
formatSize(1073741824) // → "1.00 GB"
```

### Dauer
```typescript
formatDuration(7200) // → "2h 0m"
formatDuration(150)  // → "2m 30s"
```

## Best Practices

1. **Query Invalidation**: Nach Mutationen relevante Queries invalidieren
2. **Optimistic Updates**: UI sofort aktualisieren, dann Backend-Call
3. **Error Boundaries**: Graceful Degradation bei Component-Fehlern
4. **Refetch Intervals**:
   - Status: 30s
   - Backups: 60s
   - Metriken: 5min
5. **Toast-Feedback**: Immer User-Feedback bei Aktionen

## Testing

### Unit Tests (TODO)
```bash
npm test disaster-recovery
```

### E2E Tests (TODO)
```bash
playwright test disaster-recovery
```

## Deployment

### Build
```bash
npm run build
```

### Environment-Variablen
Keine speziellen Variablen erforderlich (Backend-APIs über zentralen API-Client).

## Changelog

### Version 1.0 (2026-01-24)
- ✅ Initial Release
- ✅ 5 Core-Features implementiert
- ✅ Vollständige TypeScript-Typisierung
- ✅ Deutsche UI-Texte
- ✅ Responsive Design
- ✅ Accessibility (WCAG 2.1 AA)

## Support

Bei Fragen oder Problemen:
- Backend-API: Siehe `.claude/Docs/API/Backup-API.md`
- Frontend-Patterns: Siehe `.claude/Docs/Frontend/Patterns.md`
- Issue-Tracking: `.claude/memory/KNOWN_ISSUES.md`

---

**Entwickelt mit**: React 18, TypeScript 5, TanStack Query, shadcn/ui, Tailwind CSS
