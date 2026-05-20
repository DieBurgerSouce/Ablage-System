# Dashboard-Feature Integration Guide

Schritt-für-Schritt Anleitung zur Integration des Dashboard-Features in die bestehende Anwendung.

## 1. NPM Packages installieren

```bash
cd frontend
npm install react-grid-layout react-resizable recharts date-fns
npm install --save-dev @types/react-grid-layout @types/react-resizable
```

## 2. CSS importieren

Füge in `frontend/src/App.tsx` oder `frontend/src/main.tsx` hinzu:

```tsx
// Grid Layout Styles
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import '@/features/dashboards/dashboard-grid.css';
```

## 3. Routes erstellen

Füge in deinem Router (TanStack Router) die Dashboard-Routes hinzu:

```tsx
// frontend/src/routes/dashboards.tsx
import { createRoute } from '@tanstack/react-router';
import { rootRoute } from './root';
import {
  DashboardList,
  DashboardEditor,
  CreateDashboard,
} from '@/features/dashboards';

export const dashboardsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboards',
  component: DashboardList,
});

export const createDashboardRoute = createRoute({
  getParentRoute: () => dashboardsRoute,
  path: '/new',
  component: CreateDashboard,
});

export const editDashboardRoute = createRoute({
  getParentRoute: () => dashboardsRoute,
  path: '/$dashboardId',
  component: () => {
    const { dashboardId } = editDashboardRoute.useParams();
    return <DashboardEditor dashboardId={dashboardId} />;
  },
});

// In deinem Router-Tree registrieren:
const routeTree = rootRoute.addChildren([
  // ... andere Routes
  dashboardsRoute.addChildren([
    createDashboardRoute,
    editDashboardRoute,
  ]),
]);
```

## 4. Navigation Menu erweitern

Füge einen Link zum Dashboard im Hauptmenü hinzu:

```tsx
// In deiner Navigation/Sidebar Komponente
import { LayoutDashboard } from 'lucide-react';
import { Link } from '@tanstack/react-router';

<Link to="/dashboards">
  <LayoutDashboard className="h-5 w-5" />
  <span>Dashboards</span>
</Link>
```

## 5. Fehlende shadcn/ui Komponenten

Falls noch nicht vorhanden, installiere fehlende shadcn/ui Komponenten:

```bash
npx shadcn-ui@latest add sheet
npx shadcn-ui@latest add accordion
npx shadcn-ui@latest add scroll-area
npx shadcn-ui@latest add radio-group
npx shadcn-ui@latest add progress
npx shadcn-ui@latest add avatar
```

## 6. Backend-API URLs konfigurieren

Falls deine API-Base-URL anders ist, passe `api/index.ts` an:

```tsx
// frontend/src/features/dashboards/api/index.ts
const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/dashboards`
  : '/api/v1/dashboards';
```

## 7. Backend-Endpoints validieren

Stelle sicher, dass folgende Backend-Endpoints existieren:

### Required Endpoints
- `GET/POST /api/v1/dashboards`
- `GET/PATCH/DELETE /api/v1/dashboards/{id}`
- `POST /api/v1/dashboards/{id}/duplicate`
- `PATCH /api/v1/dashboards/{id}/favorite`
- `GET /api/v1/dashboards/shared`
- `POST /api/v1/dashboards/{id}/widgets`
- `PATCH /api/v1/dashboards/{id}/widgets/{widget_id}`
- `DELETE /api/v1/dashboards/{id}/widgets/{widget_id}`
- `PATCH /api/v1/dashboards/{id}/layout`
- `GET /api/v1/dashboards/widgets/available`
- `GET /api/v1/dashboards/presets`
- `POST /api/v1/dashboards/presets/{id}/create`
- `POST /api/v1/dashboards/{id}/share`
- `GET /api/v1/dashboards/{id}/share`
- `DELETE /api/v1/dashboards/{id}/share/{user_id}`

### Widget Data Endpoints
- `GET /api/v1/documents/stats`
- `GET /api/v1/invoices/stats`
- `GET /api/v1/cashflow/chart`
- `GET /api/v1/risk/stats`
- `GET /api/v1/workflows/stats`

## 8. TypeScript Konfiguration

Falls TypeScript Errors auftreten, stelle sicher dass `tsconfig.json` korrekt ist:

```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"],
      "@/components/*": ["./src/components/*"],
      "@/features/*": ["./src/features/*"]
    }
  }
}
```

## 9. Test-Daten (Optional)

Für Development kannst du Mock-Daten verwenden:

```tsx
// frontend/src/mocks/dashboards.ts
export const mockDashboards = [
  {
    id: '1',
    name: 'Finanz-Übersicht',
    description: 'Mein persönliches Finanz-Dashboard',
    widgets: [
      {
        id: 'w1',
        type: 'document_count',
        title: 'Dokumenten-Anzahl',
        config: {},
        x: 0,
        y: 0,
        w: 4,
        h: 2,
      },
      // ... mehr Widgets
    ],
    is_favorite: true,
    is_shared: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    owner_id: 'user-1',
    company_id: 'company-1',
  },
];
```

## 10. Environment Variables

Falls benötigt, füge in `.env` hinzu:

```bash
# Dashboard Feature
VITE_DASHBOARD_AUTO_SAVE_DELAY=1000
VITE_DASHBOARD_MAX_WIDGETS=20
```

## 11. Deployment-Checkliste

Vor dem Deployment prüfen:

- [ ] Alle NPM Packages installiert
- [ ] CSS-Imports in main.tsx/App.tsx
- [ ] Routes registriert
- [ ] Navigation-Links hinzugefügt
- [ ] Backend-Endpoints implementiert
- [ ] shadcn/ui Komponenten installiert
- [ ] TypeScript kompiliert ohne Fehler
- [ ] Build erfolgreich (`npm run build`)
- [ ] E2E Tests geschrieben (optional)

## 12. Testing

### Unit Tests

```bash
npm run test -- dashboards
```

### Integration Tests

```tsx
// frontend/tests/dashboards.spec.ts
import { test, expect } from '@playwright/test';

test('create dashboard', async ({ page }) => {
  await page.goto('/dashboards');
  await page.click('text=Neues Dashboard');
  await page.fill('input[name="name"]', 'Test Dashboard');
  await page.click('text=Dashboard erstellen');
  await expect(page).toHaveURL(/\/dashboards\/[a-z0-9-]+/);
});
```

## 13. Performance-Optimierung

### Lazy Loading

Für bessere Performance, lazy-load das Dashboard-Feature:

```tsx
// frontend/src/routes/dashboards.tsx
import { lazy } from 'react';

const DashboardList = lazy(() =>
  import('@/features/dashboards').then((m) => ({ default: m.DashboardList }))
);
```

### Code Splitting

Recharts ist groß (~150KB). Verwende dynamische Imports:

```tsx
// Im CashflowChartWidget
const { LineChart, Line, ... } = await import('recharts');
```

## 14. Troubleshooting

### Problem: Grid-Layout funktioniert nicht
**Lösung**: Prüfe ob CSS importiert ist und `WidthProvider` wrapped

### Problem: TypeScript Errors bei react-grid-layout
**Lösung**: `npm install --save-dev @types/react-grid-layout`

### Problem: Widgets rendern nicht
**Lösung**: Prüfe `switch` Statement in `DashboardEditor.tsx` und Widget-Typ

### Problem: API-Calls schlagen fehl
**Lösung**: Prüfe `credentials: 'include'` und CORS-Headers

### Problem: Dark Mode funktioniert nicht
**Lösung**: Stelle sicher dass `dark` Klasse auf `<html>` gesetzt ist

## 15. Maintenance

### Neue Widget-Typen hinzufügen

1. Type in `types/index.ts` erweitern
2. Widget-Komponente in `widgets/` erstellen
3. Switch-Case in `DashboardEditor.tsx` erweitern
4. Backend: Widget-Definition in `/widgets/available` hinzufügen

### Widget-Daten aktualisieren

Widgets laden Daten via TanStack Query. Cache-Invalidierung:

```tsx
const queryClient = useQueryClient();
queryClient.invalidateQueries({ queryKey: ['widget-data'] });
```

## Support

Bei Fragen:
- README.md im Dashboard-Feature
- shadcn/ui Docs: https://ui.shadcn.com
- react-grid-layout: https://github.com/react-grid-layout/react-grid-layout
- recharts: https://recharts.org

## Nächste Schritte

1. Backend-API implementieren (siehe Backend-Feature)
2. E2E Tests schreiben
3. Weitere Widget-Typen hinzufügen
4. Dashboard-Export/Import implementieren
5. Real-Time Updates via WebSocket
