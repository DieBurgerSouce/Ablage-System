# Dashboard Feature - Dateistruktur

Vollständige Übersicht aller erstellten Dateien für das Personalisierte Dashboards Feature.

## Verzeichnisstruktur

```
frontend/src/features/dashboards/
├── types/
│   └── index.ts                        # TypeScript Typdefinitionen (338 Zeilen)
│
├── api/
│   └── index.ts                        # API Client für alle Endpoints (286 Zeilen)
│
├── hooks/
│   └── useDashboards.ts                # TanStack Query Hooks (242 Zeilen)
│
├── components/
│   ├── DashboardList.tsx               # Dashboard-Übersicht (274 Zeilen)
│   ├── DashboardEditor.tsx             # Drag & Drop Editor (334 Zeilen)
│   ├── CreateDashboard.tsx             # Dashboard-Erstellung (269 Zeilen)
│   ├── WidgetPalette.tsx               # Widget-Auswahl Sidebar (177 Zeilen)
│   ├── ShareDashboardDialog.tsx        # Sharing-Dialog (237 Zeilen)
│   ├── DashboardSettings.tsx           # Einstellungen-Dialog (210 Zeilen)
│   ├── index.ts                        # Component Re-exports
│   └── widgets/
│       ├── WidgetWrapper.tsx           # Basis Widget-Wrapper (52 Zeilen)
│       ├── DocumentCountWidget.tsx     # Dokument-Statistik (102 Zeilen)
│       ├── InvoiceSummaryWidget.tsx    # Rechnungs-Übersicht (142 Zeilen)
│       ├── CashflowChartWidget.tsx     # Cashflow-Diagramm (164 Zeilen)
│       ├── RecentDocumentsWidget.tsx   # Neueste Dokumente (121 Zeilen)
│       ├── RiskOverviewWidget.tsx      # Risiko-Übersicht (178 Zeilen)
│       ├── WorkflowStatusWidget.tsx    # Workflow-Status (148 Zeilen)
│       └── index.ts                    # Widget Re-exports
│
├── dashboard-grid.css                  # Grid-Layout Custom Styles (169 Zeilen)
├── index.ts                            # Feature Main Export (11 Zeilen)
├── README.md                           # Feature-Dokumentation (429 Zeilen)
├── INTEGRATION.md                      # Integrations-Guide (318 Zeilen)
└── FILE_TREE.md                        # Diese Datei

GESAMT: 20 Dateien
```

## Datei-Details

### Core Files

| Datei | Zweck | Zeilen | Key Features |
|-------|-------|--------|--------------|
| `types/index.ts` | TypeScript Types | 338 | Dashboard, Widget, LayoutItem, Presets |
| `api/index.ts` | API Client | 286 | Fetch-Wrapper für alle Endpoints |
| `hooks/useDashboards.ts` | React Query Hooks | 242 | 15+ Hooks für CRUD + Sharing |
| `index.ts` | Feature Export | 11 | Re-exports aller Module |

### Component Files

| Datei | Zweck | Zeilen | Key Features |
|-------|-------|--------|--------------|
| `DashboardList.tsx` | Übersichtsliste | 274 | Tabs (Meine/Geteilt/Presets), Cards |
| `DashboardEditor.tsx` | Haupteditor | 334 | react-grid-layout, Drag & Drop |
| `CreateDashboard.tsx` | Erstellungs-Form | 269 | Blank/Preset-Auswahl |
| `WidgetPalette.tsx` | Widget-Sidebar | 177 | Kategorien, Suche, Drag & Drop |
| `ShareDashboardDialog.tsx` | Sharing | 237 | User-Suche, Permissions |
| `DashboardSettings.tsx` | Einstellungen | 210 | Name, Favorit, Duplizieren, Löschen |

### Widget Components

| Datei | Zweck | Zeilen | API Endpoint |
|-------|-------|--------|--------------|
| `WidgetWrapper.tsx` | Basis-Wrapper | 52 | N/A (UI only) |
| `DocumentCountWidget.tsx` | Dokumente | 102 | `/documents/stats` |
| `InvoiceSummaryWidget.tsx` | Rechnungen | 142 | `/invoices/stats` |
| `CashflowChartWidget.tsx` | Cashflow | 164 | `/cashflow/chart` |
| `RecentDocumentsWidget.tsx` | Neueste Docs | 121 | `/documents?limit=5` |
| `RiskOverviewWidget.tsx` | Risiko | 178 | `/risk/stats` |
| `WorkflowStatusWidget.tsx` | Workflows | 148 | `/workflows/stats` |

### Documentation & Styles

| Datei | Zweck | Zeilen | Beschreibung |
|-------|-------|--------|--------------|
| `dashboard-grid.css` | Grid Styles | 169 | react-grid-layout Customization |
| `README.md` | Feature Docs | 429 | Vollständige Dokumentation |
| `INTEGRATION.md` | Setup Guide | 318 | Schritt-für-Schritt Integration |
| `FILE_TREE.md` | Diese Datei | - | Dateistruktur-Übersicht |

## Statistiken

### Gesamt-Zeilen
```
TypeScript/TSX: ~3,500 Zeilen
CSS: ~169 Zeilen
Markdown: ~747 Zeilen
──────────────────────────
GESAMT: ~4,416 Zeilen
```

### Komponenten-Anzahl
```
React Components: 13
Custom Hooks: 15
API Functions: 20
Type Definitions: 15
```

### Dependencies

**Production:**
- react-grid-layout (^1.4.4)
- react-resizable (^3.0.5)
- recharts (^2.10.3)
- date-fns (^3.0.6)

**Development:**
- @types/react-grid-layout (^1.3.5)
- @types/react-resizable (^3.0.6)

**Existing (shadcn/ui):**
- @tanstack/react-query
- @tanstack/react-router
- lucide-react
- tailwindcss

## Import-Pfade

### Absolute Imports
```tsx
import { DashboardList } from '@/features/dashboards';
import { useDashboards } from '@/features/dashboards';
import type { Dashboard } from '@/features/dashboards';
```

### Relative Imports (intern)
```tsx
// In components/
import { WidgetWrapper } from './widgets';
import type { Widget } from '../types';
import * as api from '../api';
```

## API Endpoint Coverage

### Implementierte Endpoints (20)

**Dashboards:**
- GET /dashboards (useDashboards)
- GET /dashboards/shared (useSharedDashboards)
- GET /dashboards/{id} (useDashboard)
- POST /dashboards (useCreateDashboard)
- PATCH /dashboards/{id} (useUpdateDashboard)
- DELETE /dashboards/{id} (useDeleteDashboard)
- POST /dashboards/{id}/duplicate (useDuplicateDashboard)
- PATCH /dashboards/{id}/favorite (useSetFavorite)

**Widgets:**
- GET /dashboards/widgets/available (useAvailableWidgets)
- POST /dashboards/{id}/widgets (useAddWidget)
- PATCH /dashboards/{id}/widgets/{wid} (useUpdateWidget)
- DELETE /dashboards/{id}/widgets/{wid} (useDeleteWidget)
- PATCH /dashboards/{id}/layout (useSaveLayout)

**Sharing:**
- POST /dashboards/{id}/share (useShareDashboard)
- GET /dashboards/{id}/share (useShareInfo)
- DELETE /dashboards/{id}/share/{uid} (useUnshareDashboard)

**Presets:**
- GET /dashboards/presets (usePresets)
- POST /dashboards/presets/{id}/create (useCreateFromPreset)

**Widget Data:**
- GET /documents/stats
- GET /invoices/stats
- GET /cashflow/chart
- GET /risk/stats
- GET /workflows/stats

## Widget-Typen (7)

1. **document_count** - Dokumenten-Statistik
2. **invoice_summary** - Rechnungs-Übersicht
3. **cashflow_chart** - Cashflow-Diagramm (recharts)
4. **recent_documents** - Neueste Dokumente
5. **risk_overview** - Risiko-Übersicht
6. **workflow_status** - Workflow-Status
7. **ocr_quality** - OCR-Qualität (nicht implementiert)
8. **entity_list** - Entity-Liste (nicht implementiert)
9. **custom_chart** - Benutzerdefiniertes Diagramm (nicht implementiert)

## Testabdeckung

### Unit Tests (Empfohlen)
- [ ] `DashboardList.test.tsx`
- [ ] `DashboardEditor.test.tsx`
- [ ] `CreateDashboard.test.tsx`
- [ ] `useDashboards.test.ts`
- [ ] Widget-Komponenten Tests

### Integration Tests (Empfohlen)
- [ ] Dashboard CRUD Flow
- [ ] Widget Add/Remove Flow
- [ ] Sharing Flow
- [ ] Layout Save Flow

### E2E Tests (Optional)
- [ ] Kompletter User-Journey
- [ ] Drag & Drop Testing
- [ ] Multi-Device Testing

## Erweiterungspunkte

### Einfach hinzufügbar
- Neue Widget-Typen
- Widget-Konfiguration-Dialoge
- Dashboard-Export/Import
- Dashboard-Vorlagen Editor

### Mittlerer Aufwand
- Real-Time Updates (WebSocket)
- Erweiterte Sharing-Optionen
- Dashboard-Snapshots/Versionierung
- Collaborative Editing

### Komplexere Features
- Custom Chart Builder
- Widget Marketplace
- Dashboard-Templates Store
- Mobile App (React Native)

## Maintenance-Aufgaben

### Regelmäßig
- [ ] Dependencies aktualisieren
- [ ] Security-Updates prüfen
- [ ] Performance-Monitoring
- [ ] User-Feedback sammeln

### Bei Bedarf
- [ ] Neue Widget-Typen hinzufügen
- [ ] API-Endpoints erweitern
- [ ] UI/UX Verbesserungen
- [ ] Bug-Fixes

## Version History

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0.0 | 2026-01-19 | Initial Release |

## Lizenz

Teil des Ablage-System Projekts. Siehe Haupt-README für Lizenzinformationen.
