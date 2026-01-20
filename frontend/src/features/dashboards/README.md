# Personalisierte Dashboards Feature

Vollständige Frontend-Implementierung für personalisierte, anpassbare Dashboards mit Drag & Drop Widgets.

## Features

### ✅ Dashboard-Verwaltung
- Erstellen, Bearbeiten, Löschen von Dashboards
- Dashboard-Duplikation
- Favoriten-Markierung
- Dashboard-Sharing mit Berechtigungen (view/edit)

### ✅ Widget-System
- 7+ Widget-Typen (Dokumente, Finanzen, Workflows, Analyse)
- Drag & Drop Widget-Palette
- Resize & Reposition mit react-grid-layout
- Auto-Save Layout
- Responsive Grid (12/8/4 Spalten)

### ✅ Vorlagen (Presets)
- Vorkonfigurierte Dashboards nach Rolle
- One-Click Dashboard-Erstellung aus Vorlage

## Struktur

```
dashboards/
├── types/
│   └── index.ts              # TypeScript-Definitionen
├── api/
│   └── index.ts              # API Client (fetch)
├── hooks/
│   └── useDashboards.ts      # TanStack Query Hooks
├── components/
│   ├── DashboardList.tsx     # Übersichtsliste
│   ├── DashboardEditor.tsx   # Drag & Drop Editor
│   ├── CreateDashboard.tsx   # Erstellungs-Formular
│   ├── WidgetPalette.tsx     # Widget-Auswahl Sidebar
│   ├── ShareDashboardDialog.tsx  # Sharing-Dialog
│   ├── DashboardSettings.tsx # Einstellungen-Dialog
│   └── widgets/
│       ├── WidgetWrapper.tsx         # Basis-Wrapper
│       ├── DocumentCountWidget.tsx   # Dokument-Statistik
│       ├── InvoiceSummaryWidget.tsx  # Rechnungs-Übersicht
│       ├── CashflowChartWidget.tsx   # Cashflow-Diagramm (Recharts)
│       ├── RecentDocumentsWidget.tsx # Neueste Dokumente
│       ├── RiskOverviewWidget.tsx    # Risiko-Übersicht
│       └── WorkflowStatusWidget.tsx  # Workflow-Status
└── README.md
```

## Installation

### NPM Packages

```bash
npm install react-grid-layout react-resizable recharts date-fns
npm install --save-dev @types/react-grid-layout @types/react-resizable
```

### Package-Versionen

```json
{
  "dependencies": {
    "react-grid-layout": "^1.4.4",
    "react-resizable": "^3.0.5",
    "recharts": "^2.10.3",
    "date-fns": "^3.0.6"
  },
  "devDependencies": {
    "@types/react-grid-layout": "^1.3.5",
    "@types/react-resizable": "^3.0.6"
  }
}
```

## API Endpoints

### Dashboards
- `GET /api/v1/dashboards` - Alle eigenen Dashboards
- `GET /api/v1/dashboards/shared` - Geteilte Dashboards
- `GET /api/v1/dashboards/{id}` - Dashboard abrufen
- `POST /api/v1/dashboards` - Dashboard erstellen
- `PATCH /api/v1/dashboards/{id}` - Dashboard aktualisieren
- `DELETE /api/v1/dashboards/{id}` - Dashboard löschen
- `POST /api/v1/dashboards/{id}/duplicate` - Dashboard duplizieren
- `PATCH /api/v1/dashboards/{id}/favorite` - Favorit setzen

### Widgets
- `GET /api/v1/dashboards/widgets/available` - Verfügbare Widgets
- `POST /api/v1/dashboards/{id}/widgets` - Widget hinzufügen
- `PATCH /api/v1/dashboards/{id}/widgets/{widget_id}` - Widget aktualisieren
- `DELETE /api/v1/dashboards/{id}/widgets/{widget_id}` - Widget löschen
- `PATCH /api/v1/dashboards/{id}/layout` - Layout speichern

### Sharing
- `POST /api/v1/dashboards/{id}/share` - Dashboard teilen
- `GET /api/v1/dashboards/{id}/share` - Share-Info abrufen
- `DELETE /api/v1/dashboards/{id}/share/{user_id}` - Berechtigung entfernen

### Presets
- `GET /api/v1/dashboards/presets` - Verfügbare Vorlagen
- `POST /api/v1/dashboards/presets/{id}/create` - Aus Vorlage erstellen

## Widget-Typen

| Type | Name | Kategorie | Default-Size | API-Endpoint |
|------|------|-----------|--------------|--------------|
| `document_count` | Dokumenten-Anzahl | documents | 4x2 | `/api/v1/documents/stats` |
| `invoice_summary` | Rechnungs-Übersicht | finance | 4x3 | `/api/v1/invoices/stats` |
| `cashflow_chart` | Cashflow-Diagramm | finance | 6x3 | `/api/v1/cashflow/chart` |
| `recent_documents` | Neueste Dokumente | documents | 4x3 | `/api/v1/documents?limit=5` |
| `risk_overview` | Risiko-Übersicht | analytics | 4x3 | `/api/v1/risk/stats` |
| `workflow_status` | Workflow-Status | workflows | 4x3 | `/api/v1/workflows/stats` |

## Verwendung

### Dashboard-Liste anzeigen

```tsx
import { DashboardList } from '@/features/dashboards';

function DashboardsPage() {
  return <DashboardList />;
}
```

### Dashboard erstellen

```tsx
import { CreateDashboard } from '@/features/dashboards';

function CreateDashboardPage() {
  return <CreateDashboard />;
}
```

### Dashboard bearbeiten

```tsx
import { DashboardEditor } from '@/features/dashboards';

function EditDashboardPage({ dashboardId }: { dashboardId: string }) {
  return <DashboardEditor dashboardId={dashboardId} />;
}
```

### Hooks verwenden

```tsx
import { useDashboards, useCreateDashboard } from '@/features/dashboards';

function MyComponent() {
  const { data: dashboards, isLoading } = useDashboards();
  const createMutation = useCreateDashboard();

  const handleCreate = async () => {
    await createMutation.mutateAsync({
      name: 'Mein Dashboard',
      description: 'Test-Dashboard',
    });
  };

  return (
    <div>
      {dashboards?.map(d => <div key={d.id}>{d.name}</div>)}
      <button onClick={handleCreate}>Erstellen</button>
    </div>
  );
}
```

## Routing (TanStack Router)

```tsx
// routes/dashboards.tsx
export const DashboardsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboards',
  component: DashboardList,
});

export const CreateDashboardRoute = createRoute({
  getParentRoute: () => DashboardsRoute,
  path: '/new',
  component: CreateDashboard,
});

export const EditDashboardRoute = createRoute({
  getParentRoute: () => DashboardsRoute,
  path: '/$dashboardId',
  component: () => {
    const { dashboardId } = EditDashboardRoute.useParams();
    return <DashboardEditor dashboardId={dashboardId} />;
  },
});
```

## Grid-Layout Konfiguration

### Breakpoints
- **lg** (≥1200px): 12 Spalten
- **md** (≥996px): 8 Spalten
- **sm** (≥768px): 4 Spalten

### Row Height
- Standard: 80px
- Widgets können 2-6 Zeilen hoch sein

### Widget-Größen
- Min: 2x2 (Spalten x Zeilen)
- Default: 4x2 bis 6x3
- Max: 12x6

## Styling

Alle Komponenten nutzen **shadcn/ui** und **Tailwind CSS**:
- Card, Button, Input, Textarea
- Dialog, Sheet, AlertDialog
- Tabs, Select, Badge, Progress
- Accordion, ScrollArea

### Dark Mode Support
Alle Widgets unterstützen automatisch Dark/Light Mode via Tailwind CSS.

## Erweiterungen

### Neues Widget hinzufügen

1. **Widget-Komponente erstellen** (`widgets/MyWidget.tsx`):
```tsx
import { WidgetWrapper } from './WidgetWrapper';
import type { Widget } from '../../types';

export function MyWidget({ widget, onRemove, isEditing }: Props) {
  // Widget-Logik
  return (
    <WidgetWrapper title={widget.title} onRemove={onRemove} isEditing={isEditing}>
      {/* Content */}
    </WidgetWrapper>
  );
}
```

2. **Widget-Typ hinzufügen** (`types/index.ts`):
```tsx
export type WidgetType =
  | 'document_count'
  | 'my_widget'; // NEU
```

3. **Widget im Editor registrieren** (`DashboardEditor.tsx`):
```tsx
switch (widget.type) {
  case 'my_widget':
    return <MyWidget {...commonProps} />;
  // ...
}
```

4. **Backend: Widget-Definition** (API Endpoint):
```json
{
  "type": "my_widget",
  "name": "Mein Widget",
  "description": "Beschreibung",
  "category": "analytics",
  "defaultSize": { "w": 4, "h": 2 },
  "minSize": { "w": 2, "h": 2 }
}
```

## Performance

- **Query Caching**: TanStack Query cached alle Dashboard-Daten
- **Auto-Save**: Layout-Änderungen werden mit 1s Debounce gespeichert
- **Lazy Loading**: Widgets laden Daten nur bei Bedarf
- **Optimistic Updates**: UI aktualisiert sich sofort, Rollback bei Fehler

## Testing

### Unit Tests (Vitest)
```tsx
import { render, screen } from '@testing-library/react';
import { DashboardList } from './DashboardList';

test('renders dashboard list', () => {
  render(<DashboardList />);
  expect(screen.getByText('Dashboards')).toBeInTheDocument();
});
```

### Integration Tests
```tsx
import { useDashboards } from '../hooks/useDashboards';
import { renderHook, waitFor } from '@testing-library/react';

test('fetches dashboards', async () => {
  const { result } = renderHook(() => useDashboards());
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toHaveLength(3);
});
```

## Sicherheit

- **Multi-Tenant Isolation**: Alle API-Calls nutzen `credentials: 'include'`
- **Permission Checks**: Backend prüft Ownership und Share-Berechtigungen
- **Input-Validierung**: Formular-Validierung auf Frontend + Backend
- **XSS-Schutz**: React automatisches Escaping

## Bekannte Einschränkungen

1. **User-Suche**: ShareDashboardDialog benötigt User-Lookup-API
2. **Preset-Editor**: Admin-UI zum Erstellen von Presets fehlt noch
3. **Export/Import**: Dashboard-Export als JSON noch nicht implementiert
4. **Real-Time Updates**: Keine WebSocket-Integration für Live-Daten

## Roadmap

- [ ] Real-Time Widget-Updates (WebSocket)
- [ ] Dashboard-Templates Marketplace
- [ ] Widget-Settings Dialog (per Widget konfigurierbar)
- [ ] Custom Chart Builder
- [ ] Dashboard-Snapshots (Versionierung)
- [ ] Mobile Optimierung (Touch Drag & Drop)

## Support

Bei Fragen oder Problemen:
- Backend-API Dokumentation: `/api/v1/docs`
- Feature-Request: GitHub Issues
- Bug-Report: GitHub Issues mit Label `dashboards`
