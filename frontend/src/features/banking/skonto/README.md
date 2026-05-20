# Skonto UX Feature

Frontend-Implementierung für das Skonto-Management (Frühzahlerrabatt).

## Übersicht

Dieses Feature bietet eine vollständige UX für die Verwaltung von Skonto-Konditionen:

- **Skonto-Informationen anzeigen**: Prozentsatz, Frist, Ersparnis
- **Skonto anwenden**: Bei Zahlungseingang mit automatischer Berechnung
- **Fristen-Tracking**: Countdown und Warnungen für ablaufende Fristen
- **Verpasste Skonto**: Dashboard für nicht genutzte Möglichkeiten
- **Export**: Excel/CSV Export verpasster Skonto-Fälle

## Dateistruktur

```
skonto/
├── types.ts                          # TypeScript Typen
├── api.ts                            # API Client Funktionen
├── hooks.ts                          # React Query Hooks
├── components/
│   ├── SkontoDeadlineCounter.tsx    # Countdown-Anzeige
│   ├── ApplySkontoDialog.tsx        # Dialog zum Anwenden
│   ├── SkontoAlertBanner.tsx        # Warnbanner
│   ├── SkontoOpportunityWidget.tsx  # Dashboard Widget
│   └── index.ts                     # Barrel Export
├── MissedSkontoDashboard.tsx        # Verpasste Skonto Seite
├── index.ts                         # Feature Barrel Export
└── README.md                        # Diese Datei
```

## Komponenten

### SkontoDeadlineCounter

Countdown-Anzeige für Skonto-Frist mit Farbcodierung:
- **Grün**: >3 Tage verbleibend
- **Gelb**: 1-3 Tage verbleibend
- **Rot**: <1 Tag verbleibend oder abgelaufen

**Varianten:**
- `compact`: Nur Badge
- `full`: Card mit Details (Standard)

**Verwendung:**
```tsx
import { SkontoDeadlineCounter } from '@/features/banking/skonto';

<SkontoDeadlineCounter
  percentage={2.0}
  deadline="2026-02-14T00:00:00Z"
  amount={123.45}
  daysRemaining={3}
  isExpired={false}
  used={false}
  variant="full"
/>
```

### ApplySkontoDialog

Dialog zum Anwenden von Skonto bei Zahlung.

**Features:**
- Eingabe des gezahlten Betrags
- Optional: Zahlungsdatum
- Force-Apply für abgelaufene Fristen
- Validierung mit Toleranz (5 Cent)

**Verwendung:**
```tsx
import { ApplySkontoDialog } from '@/features/banking/skonto';

<ApplySkontoDialog
  open={dialogOpen}
  onOpenChange={setDialogOpen}
  invoiceId="uuid-..."
  skontoInfo={skontoInfo}
  onSuccess={() => refetch()}
/>
```

### SkontoAlertBanner

Warnbanner für ablaufende Skonto-Fristen.

**Features:**
- Automatische Dringlichkeitsbestimmung
- Quick-Actions (Skonto anwenden, Details)
- Optional dismissible

**Verwendung:**
```tsx
import { SkontoAlertBanner } from '@/features/banking/skonto';

<SkontoAlertBanner
  skontoInfo={skontoInfo}
  invoiceNumber="RE-2026-001"
  onApplySkonto={() => openApplyDialog()}
  onViewDetails={() => navigate('/invoices/123')}
  dismissible
/>
```

### SkontoOpportunityWidget

Dashboard Widget für bevorstehende Skonto-Fristen.

**Features:**
- Top-N Skonto-Gelegenheiten
- Sortiert nach Dringlichkeit
- Gesamtsumme potentieller Ersparnisse
- Quick-Links zu Rechnungen

**Verwendung:**
```tsx
import { SkontoOpportunityWidget } from '@/features/banking/skonto';

<SkontoOpportunityWidget
  daysAhead={7}
  limit={5}
/>
```

### MissedSkontoDashboard

Vollständige Seite für verpasste Skonto-Möglichkeiten.

**Features:**
- Statistik-Cards (Anzahl, Summe, Durchschnitt)
- Zeitraum-Filter
- Sortierbare Tabelle
- Excel/CSV Export
- Pagination

**Verwendung:**
```tsx
import { MissedSkontoDashboard } from '@/features/banking/skonto';

// In Route Definition:
<Route path="/banking/skonto/missed" component={MissedSkontoDashboard} />
```

## Hooks

### useSkontoInfo

Holt Skonto-Informationen für eine Rechnung.

```tsx
const { data: skontoInfo, isLoading } = useSkontoInfo(invoiceId);
```

### useSetSkonto

Setzt Skonto-Konditionen für eine Rechnung.

```tsx
const setSkonto = useSetSkonto();

await setSkonto.mutateAsync({
  invoiceId: 'uuid-...',
  data: {
    skontoPercentage: 2.0,
    skontoDays: 10,
    netDays: 30,
  },
});
```

### useApplySkonto

Wendet Skonto bei Zahlung an.

```tsx
const applySkonto = useApplySkonto();

await applySkonto.mutateAsync({
  invoiceId: 'uuid-...',
  data: {
    paymentAmount: 980.00,
    paymentDate: '2026-01-23',
    forceApply: false,
  },
});
```

### useUpcomingSkonto

Holt bevorstehende Skonto-Fristen.

```tsx
const { data: opportunities } = useUpcomingSkonto(7, 20);
```

### useMissedSkonto

Holt verpasste Skonto-Möglichkeiten mit Pagination.

```tsx
const { data: missedSkonto } = useMissedSkonto({
  startDate: '2025-01-01',
  endDate: '2026-01-23',
  page: 1,
  perPage: 20,
});
```

### useExportMissedSkonto

Exportiert verpasste Skonto-Daten.

```tsx
const exportMutation = useExportMissedSkonto();

await exportMutation.mutateAsync({
  format: 'xlsx',
  filter: {
    startDate: '2025-01-01',
    endDate: '2026-01-23',
  },
});
```

## API Endpoints

Alle API-Funktionen sind in `api.ts` dokumentiert:

- `GET /api/v1/invoices/{id}/skonto` - Skonto-Info abrufen
- `PATCH /api/v1/invoices/{id}/skonto` - Skonto setzen
- `POST /api/v1/invoices/{id}/apply-skonto` - Skonto anwenden
- `GET /api/v1/invoices/skonto/upcoming` - Bevorstehende Fristen
- `GET /api/v1/invoices/skonto/missed` - Verpasste Skonto
- `GET /api/v1/invoices/skonto/statistics` - Statistiken
- `GET /api/v1/invoices/skonto/monthly-summary` - Monatliche Zusammenfassung
- `GET /api/v1/invoices/skonto/missed/export` - Export (Blob)

## Typen

Alle TypeScript-Typen sind in `types.ts` vollständig dokumentiert:

- `SkontoInfo` - Skonto-Informationen
- `SkontoOpportunity` - Bevorstehende Gelegenheit
- `MissedSkontoItem` - Verpasste Skonto-Rechnung
- `SkontoStatistics` - Statistiken
- Und mehr...

## Farbcodierung

Das Feature nutzt konsistente Farbcodierung (definiert in `SKONTO_COLORS`):

- **Grün** (`active`): Skonto aktiv, >3 Tage
- **Gelb** (`expiring`): Skonto läuft bald ab, 1-3 Tage
- **Rot** (`expired`): Skonto abgelaufen
- **Blau** (`used`): Skonto bereits genutzt

## Integration Beispiel

```tsx
// In einer Rechnungsdetail-Seite:
import {
  useSkontoInfo,
  SkontoDeadlineCounter,
  SkontoAlertBanner,
  ApplySkontoDialog,
} from '@/features/banking/skonto';

function InvoiceDetailPage({ invoiceId }) {
  const { data: skontoInfo } = useSkontoInfo(invoiceId);
  const [applyDialogOpen, setApplyDialogOpen] = useState(false);

  if (!skontoInfo) return null;

  return (
    <div>
      {/* Warnung bei ablaufender Frist */}
      <SkontoAlertBanner
        skontoInfo={skontoInfo}
        onApplySkonto={() => setApplyDialogOpen(true)}
      />

      {/* Countdown-Anzeige */}
      <SkontoDeadlineCounter
        percentage={skontoInfo.percentage}
        deadline={skontoInfo.deadline}
        amount={skontoInfo.amount}
        daysRemaining={skontoInfo.daysRemaining}
        isExpired={skontoInfo.isExpired}
        used={skontoInfo.used}
      />

      {/* Apply Dialog */}
      <ApplySkontoDialog
        open={applyDialogOpen}
        onOpenChange={setApplyDialogOpen}
        invoiceId={invoiceId}
        skontoInfo={skontoInfo}
      />
    </div>
  );
}
```

## Testing

Alle Komponenten sind so konzipiert, dass sie leicht testbar sind:

- Pure Functions in `api.ts`
- Isolierte React Query Hooks
- Komponenten mit Props-Injection
- Mock-friendly API Client

Beispiel Test:

```tsx
import { render, screen } from '@testing-library/react';
import { SkontoDeadlineCounter } from './components/SkontoDeadlineCounter';

test('zeigt Skonto-Countdown an', () => {
  render(
    <SkontoDeadlineCounter
      percentage={2.0}
      deadline="2026-02-14T00:00:00Z"
      amount={123.45}
      daysRemaining={3}
      isExpired={false}
      used={false}
    />
  );

  expect(screen.getByText(/2% Skonto/)).toBeInTheDocument();
  expect(screen.getByText(/3 Tage/)).toBeInTheDocument();
});
```

## Wartung

### Backend-Änderungen

Bei Änderungen am Backend:

1. Typen in `types.ts` aktualisieren
2. API-Funktionen in `api.ts` anpassen
3. Snake_case → camelCase Transformation prüfen

### Neue Features

Neue Features sollten:

1. Typen in `types.ts` definieren
2. API-Funktion in `api.ts` hinzufügen
3. Hook in `hooks.ts` erstellen
4. Komponente in `components/` implementieren
5. In `index.ts` exportieren

## Performance

- **Query Caching**: 5-10 Minuten (konfigurierbar)
- **Auto-Refetch**: Bei relevanten Mutations
- **Pagination**: Standard 20 Items/Page
- **Lazy Loading**: Komponenten nur wenn benötigt

## Accessibility

Alle Komponenten folgen WCAG 2.1 AA:

- Semantisches HTML
- ARIA Labels
- Keyboard-Navigation
- Farbkontrast >4.5:1
- Screen-Reader Support

## Lizenz

Siehe Root `LICENSE` Datei.
